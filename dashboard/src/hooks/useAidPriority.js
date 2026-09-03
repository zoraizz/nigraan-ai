import { useCallback, useEffect, useState } from 'react'
import { rankPriority } from '../api/aidPriority.js'

// District ranking via Aid Priority (POST /rank-priority).
//   useAidPriority(districts) -> { ranking, scoring, loading, error, refetch }
// - districts: array of assessment payloads ({ district, hazard_type,
//   risk_level, damage_breakdown | overall_damage_level, ... }); pass an
//   empty array or null to idle the hook (no request).
// - ranking: the response's ranked_districts array (already sorted)
// - scoring: the transparency metadata block (formula, weights, notes)
// - refetch(): re-POST the current payload
// The payload is JSON-serialized for effect comparison, so passing a freshly
// built array literal will not re-request on every render.
export function useAidPriority(districts) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)

  const serialized = JSON.stringify(districts ?? [])

  useEffect(() => {
    const payload = JSON.parse(serialized)
    if (payload.length === 0) {
      setData(null)
      setError(null)
      setLoading(false)
      return undefined
    }

    let active = true
    setLoading(true)
    setError(null)
    rankPriority(payload)
      .then((body) => {
        if (!active) return
        setData(body)
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err)
        setLoading(false)
      })

    return () => {
      active = false
    }
  }, [serialized, tick])

  const refetch = useCallback(() => setTick((t) => t + 1), [])

  return {
    ranking: data?.ranked_districts ?? [],
    scoring: data?.scoring ?? null,
    loading,
    error,
    refetch,
  }
}
