// Damage Checker service (port 8001) — satellite image damage classification.
import { ENDPOINTS } from '../config/endpoints.js'
import { postForm } from './client.js'

// POST /classify-damage
// Multipart form with the image file; `area` is an optional query param
// (district label passed through to the response, defaults to 'unknown'
// server-side).
// Response: { damage_level: 'none'|'partial'|'destroyed', confidence, area }
export function classifyDamage(imageFile, area) {
  const path = area
    ? `/classify-damage?area=${encodeURIComponent(area)}`
    : '/classify-damage'
  const form = new FormData()
  form.append('image', imageFile)
  return postForm(ENDPOINTS.damageApi, path, form)
}
