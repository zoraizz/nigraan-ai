import { useEffect, useState } from 'react'
import { postWhatIf } from '../api/floodTracker.js'

// flood: a synthetic peak routed downstream (POST /what-if).
//   useWhatIf(body) -> { situation, loading, error }
// Pass null to idle (no scenario run yet). body is compared as JSON so the
// same scenario is not re-posted on every render.
export function useWhatIf(body) {
  const serialized = JSON.stringify(body ?? null)
  const [state, setState] = useState({ situation: null, loading: false, error: null })

  useEffect(() => {
    const payload = JSON.parse(serialized)
    if (!payload) {
      setState({ situation: null, loading: false, error: null })
      return undefined
    }
    let active = true
    setState((current) => ({ ...current, loading: true, error: null }))
    postWhatIf(payload)
      .then((situation) => {
        if (active) setState({ situation, loading: false, error: null })
      })
      .catch((err) => {
        if (active) setState({ situation: null, loading: false, error: err })
      })
    return () => {
      active = false
    }
  }, [serialized])

  return state
}
