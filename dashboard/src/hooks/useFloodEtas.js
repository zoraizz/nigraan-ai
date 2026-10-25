import { useEffect, useState } from 'react'
import { FLOOD_USE_FIXTURES, getDistrictFloodEtas, lastFloodAsOf } from '../api/floodTracker.js'

// flood: district ETAs from the River Flood Tracker for Aid Priority.
//   useFloodEtas() -> { settled, asOf, etas, error }
// - asOf: the replay step last viewed on the Flood Tracker page
// - etas: { "<district>": hours } (modelled), {} when unavailable
// - settled: true once the request finished, failed or timed out, so the
//   ranking never waits on a service that is down
// Fixture mode returns no ETAs: hand-made fixtures must not move a ranking.
// health: Flood Tracker's warm-up status. The request waits while it is
// 'pending'; on 'timeout' it is skipped (skipped: true, no ETAs).
const TIMEOUT_MS = 5000

export function useFloodEtas(health = 'up') {
  const [state, setState] = useState(() => ({
    settled: FLOOD_USE_FIXTURES,
    asOf: lastFloodAsOf(),
    etas: {},
    error: null,
  }))

  useEffect(() => {
    if (FLOOD_USE_FIXTURES || health === 'pending') return undefined
    if (health === 'timeout') {
      setState((current) => ({ ...current, settled: true, etas: {}, skipped: true }))
      return undefined
    }
    let active = true
    let timer
    const timeout = new Promise((_, reject) => {
      timer = window.setTimeout(() => reject(new Error('River Flood Tracker did not answer in time')), TIMEOUT_MS)
    })
    Promise.race([getDistrictFloodEtas(lastFloodAsOf()), timeout])
      .then(({ asOf, etas }) => {
        if (active) setState({ settled: true, asOf, etas, error: null })
      })
      .catch((err) => {
        if (active) setState((current) => ({ ...current, settled: true, etas: {}, error: err }))
      })
      .finally(() => window.clearTimeout(timer))
    return () => {
      active = false
    }
  }, [health])

  return state
}
