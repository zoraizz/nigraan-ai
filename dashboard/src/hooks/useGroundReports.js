import { useCallback, useEffect, useState } from 'react'
import { getGroundSummary, listGroundReports } from '../api/groundIntake.js'

// Ground report list and district summary, loaded together.
//   useGroundReports(filters) -> { reports, summary, loading, error, refetch }
// - filters: { district, status, urgent, include_duplicates }; omit to load all.
// - reports: the JSON list from GET /ground-reports (empty when the body is not a list).
// - summary: the GET /ground-summary body, or null before the first success.
// - refetch(): run both requests again.
// The filters object is JSON-serialized for effect comparison, so a fresh
// object literal with the same fields will not re-request on every render.
export function useGroundReports(filters) {
  const [reports, setReports] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)

  const serialized = JSON.stringify(filters ?? {})

  useEffect(() => {
    const parsed = JSON.parse(serialized)
    let active = true
    setLoading(true)
    setError(null)
    Promise.all([
      listGroundReports(parsed),
      getGroundSummary(parsed.district),
    ])
      .then(([reportBody, summaryBody]) => {
        if (!active) return
        setReports(Array.isArray(reportBody) ? reportBody : [])
        setSummary(summaryBody ?? null)
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

  const refetch = useCallback(() => setTick((value) => value + 1), [])

  return { reports, summary, loading, error, refetch }
}
