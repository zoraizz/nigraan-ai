import { useCallback, useEffect, useState } from 'react'
import { FLOOD_USE_FIXTURES, getReplay2022 } from '../api/floodTracker.js'

// The 2022 demo opens on the morning the wave is in the upper-middle Indus.
const OPEN_ON = '2022-08-29'
export const REPLAY_STEP_MS = 800

function openingIndex(steps) {
  const found = steps.findIndex((step) => String(step?.as_of || '').startsWith(OPEN_ON))
  return found >= 0 ? found : 0
}

// Loads GET /replay/2022 once. The slider and play control only change `index`;
// they do not call the API again. Each step is already a flood-situation object.
export function useFloodReplay() {
  const [replay, setReplay] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    getReplay2022()
      .then((body) => {
        if (!active) return
        const steps = Array.isArray(body?.steps) ? body.steps : []
        setReplay({
          steps,
          scorecard: Array.isArray(body?.scorecard) ? body.scorecard : [],
          fixture: body?.fixture === true,
        })
        setIndex(openingIndex(steps))
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
  }, [])

  const stepCount = replay?.steps?.length ?? 0

  useEffect(() => {
    if (!playing || stepCount === 0) return undefined
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1 < stepCount ? current + 1 : current))
    }, REPLAY_STEP_MS)
    return () => window.clearInterval(id)
  }, [playing, stepCount])

  useEffect(() => {
    if (playing && stepCount > 0 && index >= stepCount - 1) {
      setPlaying(false)
    }
  }, [playing, index, stepCount])

  const scrub = useCallback((next) => {
    const last = Math.max(0, stepCount - 1)
    const clamped = Math.min(last, Math.max(0, next))
    setPlaying(false)
    setIndex(clamped)
  }, [stepCount])

  const togglePlay = useCallback(() => {
    if (stepCount === 0) return
    if (!playing && index >= stepCount - 1) {
      setIndex(0)
      setPlaying(true)
      return
    }
    setPlaying((current) => !current)
  }, [playing, index, stepCount])

  return {
    situation: replay?.steps?.[index] ?? null,
    steps: replay?.steps ?? [],
    scorecard: replay?.scorecard ?? [],
    index,
    playing,
    loading,
    error,
    usingFixtures: FLOOD_USE_FIXTURES || replay?.fixture === true,
    scrub,
    togglePlay,
  }
}
