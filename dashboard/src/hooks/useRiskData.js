import { useCallback, useEffect, useState } from 'react'
import { predictRisk } from '../api/riskFlag.js'

// Live risk prediction for a single district via Risk Flag (POST /predict-risk).
//   useRiskData(district) -> { data, loading, error, refetch }
// - data: /predict-risk response body (risk_level, reason, rainfall fields)
// - error: ApiError from ../api/client.js (network failure or non-2xx)
// - refetch(): re-run the request for the current district
// Pass a falsy district to idle the hook (no request, data cleared).
// Risk Flag fetches Open-Meteo rainfall (and may call Gemini) server-side,
// so requests can take several minutes — consumers should show a loading
// state rather than assume instant resolution.
export function useRiskData(district) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(Boolean(district))
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  // Elapsed-seconds counter: ticks up every 1 s while loading, resets on settle.
  useEffect(() => {
    if (!loading) { setElapsed(0); return undefined }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [loading])

  useEffect(() => {
    if (!district) {
      setData(null)
      setError(null)
      setLoading(false)
      return undefined
    }

    let active = true
    setLoading(true)
    setError(null)
    predictRisk(district)
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

    // Ignore stale responses after the district (or tick) changes.
    return () => {
      active = false
    }
  }, [district, tick])

  const refetch = useCallback(() => setTick((t) => t + 1), [])
  return { data, loading, error, refetch, elapsed }
}
