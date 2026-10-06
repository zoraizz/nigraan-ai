import { useCallback, useEffect, useState } from 'react'
import { checkDamageHealth, classifyScene } from '../api/damageChecker.js'

// Scene classification via POST /classify-scene.
// When `active` becomes true, GET /health wakes a cold Damage Checker.
//   useSceneClassification(active) -> { result, loading, error, wake, wakeError, classify, reset }
export function useSceneClassification(active) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [wake, setWake] = useState('idle')
  const [wakeError, setWakeError] = useState(null)

  useEffect(() => {
    if (!active) return undefined
    let cancelled = false
    setWake('waking')
    setWakeError(null)
    checkDamageHealth()
      .then(() => {
        if (!cancelled) setWake('awake')
      })
      .catch((err) => {
        if (!cancelled) {
          setWake('error')
          setWakeError(err)
        }
      })
    return () => {
      cancelled = true
    }
  }, [active])

  const classify = useCallback(async (imageFile, tileSize, area) => {
    if (!imageFile) {
      setError(new Error('No image selected'))
      return null
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const body = await classifyScene(imageFile, tileSize, area)
      setResult(body)
      return body
    } catch (err) {
      setError(err)
      setResult(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return { result, loading, error, wake, wakeError, classify, reset }
}
