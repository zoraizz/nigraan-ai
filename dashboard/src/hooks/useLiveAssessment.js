import { useCallback, useEffect, useState } from 'react'
import { predictRisk } from '../api/riskFlag.js'
import { classifyDamage } from '../api/damageChecker.js'
import { SAMPLE_PAIRING, hazardTypeFor } from '../config/samplePairing.js'

// Live cross-module assessment assembler for Aid Priority.
//   useLiveAssessment() -> { phase, progress, payload, error, elapsed, run, reset }
// - run(): for every district in SAMPLE_PAIRING (in parallel), fetches its
//   real sample tile (dev-server /sample-images route), classifies it live
//   via POST /classify-damage, and calls POST /predict-risk (Risk Flag,
//   Gemini-backed, cached server-side for 15 min). On success `payload`
//   holds the /rank-priority districts array (single-tile damage mode),
//   ready for useAidPriority.
// - progress: per-district status for the loading panel. Each row is
//   { district, risk, damage, risk_level, risk_cached, damage_level,
//     confidence } where risk/damage are 'pending' | 'ok' | 'error'.
// - phase: 'idle' | 'assembling' | 'done' | 'error'
// A cold server cache makes /predict-risk take minutes per district (Gemini
// latency); pre-warm the districts (Risk Flag cache) before demoing.
export function useLiveAssessment() {
  const [phase, setPhase] = useState('idle')
  const [progress, setProgress] = useState([])
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(0)

  // Elapsed-seconds counter while assembling (same pattern as useRiskData).
  useEffect(() => {
    if (phase !== 'assembling') {
      setElapsed(0)
      return undefined
    }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [phase])

  const run = useCallback(async () => {
    setPhase('assembling')
    setError(null)
    setPayload(null)
    setProgress(SAMPLE_PAIRING.map((entry) => ({
      district: entry.district,
      risk: 'pending',
      damage: 'pending',
      risk_level: null,
      risk_cached: null,
      damage_level: null,
      confidence: null,
    })))

    const settle = (district, patch) => setProgress((rows) => rows.map(
      (row) => (row.district === district ? { ...row, ...patch } : row),
    ))

    const results = await Promise.allSettled(SAMPLE_PAIRING.map(async (entry) => {
      // 1. Fetch the district's real sample tile from the dev server.
      const tileUrl = `/sample-images/${entry.tile}`
      const tileResponse = await fetch(tileUrl)
      if (!tileResponse.ok) {
        settle(entry.district, { damage: 'error' })
        throw new Error(
          `sample tile not available at ${tileUrl} (served by the dev server from damage-checker/sample-images/)`,
        )
      }
      const blob = await tileResponse.blob()
      const tileFile = new File([blob], entry.tile, { type: 'image/png' })

      // 2. Risk Flag + Damage Checker in parallel for this district. Each
      //    leg settles its own progress entry so a partial failure is
      //    visible in the loading panel.
      const riskPromise = predictRisk(entry.district)
        .then((risk) => {
          settle(entry.district, {
            risk: 'ok',
            risk_level: risk.risk_level,
            risk_cached: Boolean(risk.cached),
          })
          return risk
        })
        .catch((err) => {
          settle(entry.district, { risk: 'error' })
          throw err
        })
      const damagePromise = classifyDamage(tileFile, entry.district)
        .then((damage) => {
          settle(entry.district, {
            damage: 'ok',
            damage_level: damage.damage_level,
            confidence: damage.confidence,
          })
          return damage
        })
        .catch((err) => {
          settle(entry.district, { damage: 'error' })
          throw err
        })

      const [risk, damage] = await Promise.all([riskPromise, damagePromise])
      return { entry, risk, damage }
    }))

    const failures = results
      .map((result, index) => ({ result, district: SAMPLE_PAIRING[index].district }))
      .filter((item) => item.result.status === 'rejected')
    if (failures.length > 0) {
      const details = failures
        .map((item) => `${item.district}: ${item.result.reason?.message ?? item.result.reason}`)
        .join(' | ')
      setError(new Error(`Live assessment failed (${details})`))
      setPhase('error')
      return
    }

    // 3. Assemble the /rank-priority payload (single-tile damage mode).
    setPayload(results.map((item) => {
      const { entry, risk, damage } = item.value
      return {
        district: entry.district,
        hazard_type: hazardTypeFor(entry.district),
        risk_level: risk.risk_level,
        overall_damage_level: damage.damage_level,
        confidence: damage.confidence,
      }
    }))
    setPhase('done')
  }, [])

  const reset = useCallback(() => {
    setPhase('idle')
    setProgress([])
    setPayload(null)
    setError(null)
  }, [])

  return { phase, progress, payload, error, elapsed, run, reset }
}
