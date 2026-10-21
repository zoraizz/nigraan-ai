import { useEffect, useState } from 'react'
import { postAlertDrafts } from '../api/floodTracker.js'

// Urdu/Sindhi drafts for one village or one district.
//   useAlertDrafts(body) -> { drafts, loading, error }
// Pass null to idle (drawer closed, no request). body is compared as JSON
// so a freshly built object with the same fields does not re-POST.
export function useAlertDrafts(body) {
  const serialized = JSON.stringify(body ?? null)
  const [drafts, setDrafts] = useState([])
  const [error, setError] = useState(null)
  // Null until the effect for this payload settles, so the first paint
  // does not flash "no draft" before the request starts.
  const [settledFor, setSettledFor] = useState(null)

  useEffect(() => {
    const payload = JSON.parse(serialized)
    if (!payload) {
      setDrafts([])
      setError(null)
      setSettledFor(serialized)
      return undefined
    }

    let active = true
    setError(null)
    postAlertDrafts(payload)
      .then((response) => {
        if (!active) return
        setDrafts(Array.isArray(response?.drafts) ? response.drafts : [])
        setError(null)
        setSettledFor(serialized)
      })
      .catch((err) => {
        if (!active) return
        setError(err)
        setDrafts([])
        setSettledFor(serialized)
      })

    return () => {
      active = false
    }
  }, [serialized])

  const pending = settledFor !== serialized
  return {
    drafts: pending ? [] : drafts,
    loading: pending && serialized !== 'null',
    error: pending ? null : error,
  }
}
