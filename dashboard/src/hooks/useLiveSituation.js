import { useEffect, useState } from 'react'
import { getLiveSituation } from '../api/floodTracker.js'

// flood: today's modelled situation (GET /flood-situation?mode=live).
//   useLiveSituation(enabled) -> { situation, loading, error, unavailable }
// - enabled: false until the Today view is shown, so the replay demo never
//   waits on (or fails because of) the GloFAS fetch
// - unavailable: true on 503 live_unavailable (and in fixture mode)
export function useLiveSituation(enabled) {
  const [state, setState] = useState({ situation: null, loading: false, error: null })

  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    setState((current) => ({ ...current, loading: true, error: null }))
    getLiveSituation()
      .then((situation) => {
        if (active) setState({ situation, loading: false, error: null })
      })
      .catch((err) => {
        if (active) setState({ situation: null, loading: false, error: err })
      })
    return () => {
      active = false
    }
  }, [enabled])

  return {
    ...state,
    unavailable: state.error?.status === 503,
  }
}
