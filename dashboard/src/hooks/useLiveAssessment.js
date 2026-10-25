import { useCallback, useEffect, useRef, useState } from 'react'
import { predictRisk } from '../api/riskFlag.js'
import { classifyDamage } from '../api/damageChecker.js'
import { getGroundSummary } from '../api/groundIntake.js'
import { SAMPLE_PAIRING, hazardTypeFor } from '../config/samplePairing.js'

// ground: /rank-priority ground_evidence from GET /ground-summary, or null
// when the district has no unique non-rejected report (field then omitted).
function groundEvidenceFor(summary, district) {
  const row = summary?.districts?.[district]
  if (!row || !(row.report_count >= 1)) return null
  const mix = row.severity_mix ?? {}
  return {
    none: mix.none ?? 0,
    partial: mix.partial ?? 0,
    destroyed: mix.destroyed ?? 0,
    verified_count: row.verified_count ?? 0,
    urgent_open: row.urgent_open ?? 0,
  }
}

// Districts the live ranking will assess. A stored scene replaces that
// district's sample tile. A district outside the demo pairing is added.
function assessmentPlan(sceneDamage) {
  const rows = SAMPLE_PAIRING.map((entry) => ({
    district: entry.district,
    tile: entry.tile,
    source: sceneDamage?.district === entry.district ? 'scene' : 'sample',
  }))
  if (sceneDamage && !rows.some((row) => row.district === sceneDamage.district)) {
    rows.push({
      district: sceneDamage.district,
      tile: null,
      source: 'scene',
    })
  }
  return rows
}

// Live cross-module assessment assembler for Aid Priority.
//   useLiveAssessment(sceneDamage) -> { phase, progress, payload, error, elapsed, run, reset }
// - sceneDamage: { district, damage_breakdown, tile_count, truncated } | null,
//   stored from a scene classification. That district skips POST /classify-damage
//   and submits damage_breakdown + tile_count (never overall_damage_level).
// - run(): for every planned district (in parallel), calls POST /predict-risk.
//   Sample districts also classify their bundled tile. On success `payload`
//   holds the /rank-priority districts array.
// - progress: per-district status. damage_source is 'scene' | 'sample'.
// - phase: 'idle' | 'assembling' | 'done' | 'error'
// - includeGround: also fetch GET /ground-summary and add ground_evidence to
//   each planned district with report_count >= 1. If that request fails the
//   run still ranks without ground_evidence and `groundError` holds the reason.
export function useLiveAssessment(sceneDamage, { includeGround = false } = {}) {
  const [phase, setPhase] = useState('idle')
  const [progress, setProgress] = useState([])
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [groundError, setGroundError] = useState(null)
  const runId = useRef(0)

  useEffect(() => {
    if (phase !== 'assembling') {
      setElapsed(0)
      return undefined
    }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [phase])

  const run = useCallback(async () => {
    const id = ++runId.current
    const plan = assessmentPlan(sceneDamage)
    setPhase('assembling')
    setError(null)
    setGroundError(null)
    setPayload(null)
    setProgress(plan.map((entry) => ({
      district: entry.district,
      risk: 'pending',
      damage: entry.source === 'scene' ? 'ok' : 'pending',
      damage_source: entry.source,
      truncated: entry.source === 'scene' ? Boolean(sceneDamage?.truncated) : false,
      risk_level: null,
      risk_cached: null,
      damage_level: null,
      confidence: null,
    })))

    const settle = (district, patch) => {
      if (runId.current !== id) return
      setProgress((rows) => rows.map(
        (row) => (row.district === district ? { ...row, ...patch } : row),
      ))
    }

    const groundPromise = includeGround ? getGroundSummary() : Promise.resolve(null)

    const results = await Promise.allSettled(plan.map(async (entry) => {
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

      if (entry.source === 'scene') {
        const risk = await riskPromise
        return { entry, risk, damage: null }
      }

      const tileUrl = `/sample-images/${entry.tile}`
      const tileResponse = await fetch(tileUrl)
      if (!tileResponse.ok) {
        settle(entry.district, { damage: 'error' })
        throw new Error(`the sample image for ${entry.district} could not be loaded`)
      }
      const blob = await tileResponse.blob()
      const tileFile = new File([blob], entry.tile, { type: 'image/png' })

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
      .map((result, index) => ({ result, district: plan[index].district }))
      .filter((item) => item.result.status === 'rejected')
    // ground: a failed summary never fails the run; rank without it.
    const [groundResult] = await Promise.allSettled([groundPromise])
    if (runId.current !== id) return
    setGroundError(groundResult.status === 'rejected'
      ? String(groundResult.reason?.message ?? groundResult.reason)
      : null)
    if (failures.length > 0) {
      // Group districts that failed with the same message, so one service
      // outage reads as one line instead of five copies.
      const byMessage = new Map()
      failures.forEach((item) => {
        const message = String(item.result.reason?.message ?? item.result.reason)
        byMessage.set(message, [...(byMessage.get(message) ?? []), item.district])
      })
      const details = [...byMessage]
        .map(([message, districts]) => `${districts.join(', ')}: ${message}`)
        .join(' | ')
      setError(new Error(details))
      setPhase('error')
      return
    }

    const groundSummary = groundResult.status === 'fulfilled' ? groundResult.value : null
    setPayload(results.map((item) => {
      const row = assessmentRow(item.value)
      const ground = groundEvidenceFor(groundSummary, row.district)
      return ground ? { ...row, ground_evidence: ground } : row
    }))
    setPhase('done')

    function assessmentRow({ entry, risk, damage }) {
      if (entry.source === 'scene') {
        return {
          district: entry.district,
          hazard_type: hazardTypeFor(entry.district),
          risk_level: risk.risk_level,
          damage_breakdown: {
            none: sceneDamage.damage_breakdown.none,
            partial: sceneDamage.damage_breakdown.partial,
            destroyed: sceneDamage.damage_breakdown.destroyed,
          },
          tile_count: sceneDamage.tile_count,
        }
      }
      return {
        district: entry.district,
        hazard_type: hazardTypeFor(entry.district),
        risk_level: risk.risk_level,
        overall_damage_level: damage.damage_level,
        confidence: damage.confidence,
      }
    }
  }, [sceneDamage, includeGround])

  const reset = useCallback(() => {
    runId.current += 1
    setPhase('idle')
    setProgress([])
    setPayload(null)
    setError(null)
    setGroundError(null)
  }, [])

  return { phase, progress, payload, error, groundError, elapsed, run, reset }
}
