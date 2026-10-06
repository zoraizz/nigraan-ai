// Damage Checker service (port 8001) — satellite image damage classification.
import { ENDPOINTS } from '../config/endpoints.js'
import { getJson, postForm } from './client.js'

// GET /health — wakes a cold Render instance. The first call after idle
// can take about a minute while the process and model come up.
export function checkDamageHealth() {
  return getJson(ENDPOINTS.damageApi, '/health')
}

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

// POST /classify-scene
// One large image, cut into non-overlapping tiles. `tileSize` is 256, 512,
// or 1024 (server default 512). `area` is an optional passthrough label.
// Response: grid, per-tile labels, damage_breakdown, percent_damaged.
// A time-budget stop is HTTP 200 with truncated: true, not an error.
// 413 / 422 bodies carry the env-configured limit in `error` (a string).
export function classifyScene(imageFile, tileSize = 512, area) {
  const params = new URLSearchParams()
  params.set('tile_size', String(tileSize))
  if (area) params.set('area', area)
  const form = new FormData()
  form.append('image', imageFile)
  return postForm(ENDPOINTS.damageApi, `/classify-scene?${params.toString()}`, form)
}
