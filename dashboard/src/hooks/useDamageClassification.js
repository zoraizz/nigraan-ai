import { useCallback, useState } from 'react'
import { classifyDamage } from '../api/damageChecker.js'

// Damage classification via Damage Checker (POST /classify-damage, multipart).
//   useDamageClassification() -> { result, loading, error, classify, reset }
// - classify(imageFile, area?): uploads the file (area is an optional
//   passthrough district label). Resolves to the response body
//   ({ damage_level, confidence, area }) or null on failure — the error
//   state carries the ApiError either way.
// - reset(): clears result + error (e.g., when a new file is selected)
export function useDamageClassification() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const classify = useCallback(async (imageFile, area) => {
    if (!imageFile) {
      setError(new Error('No image selected'))
      return null
    }
    setLoading(true)
    setError(null)
    try {
      const body = await classifyDamage(imageFile, area)
      setResult(body)
      return body
    } catch (err) {
      setError(err)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return { result, loading, error, classify, reset }
}
