// Ground Photo Intake on the Damage Checker service (port 8001).
// POST /intake, GET /ground-reports, GET /ground-summary, PATCH .../review.
// Base URL is ENDPOINTS.damageApi. Satellite classify routes are not called here.
import { ENDPOINTS } from '../config/endpoints.js'
import { getJson, patchJson, postForm } from './client.js'

function withQuery(path, params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `${path}?${text}` : path
}

// POST /intake — multipart field "image". Location and role are query params.
// Response is one of route satellite | ground | irrelevant. See API contract.
export function submitGroundPhoto(file, { district, village, lat, lon, reporterRole } = {}) {
  const path = withQuery('/intake', {
    district,
    village,
    lat,
    lon,
    reporter_role: reporterRole,
  })
  const form = new FormData()
  form.append('image', file)
  return postForm(ENDPOINTS.damageApi, path, form)
}

// GET /ground-reports — JSON list. Default server list omits duplicates.
// filters: { district, status, urgent, include_duplicates }
export function listGroundReports(filters = {}) {
  const path = withQuery('/ground-reports', {
    district: filters.district,
    status: filters.status,
    urgent: filters.urgent,
    include_duplicates: filters.include_duplicates,
  })
  return getJson(ENDPOINTS.damageApi, path)
}

export function getGroundReport(id) {
  return getJson(ENDPOINTS.damageApi, `/ground-reports/${encodeURIComponent(id)}`)
}

// PATCH /ground-reports/{id}/review
// body: { action, corrections?, note?, officer? }
export function reviewGroundReport(id, body) {
  return patchJson(
    ENDPOINTS.damageApi,
    `/ground-reports/${encodeURIComponent(id)}/review`,
    body,
  )
}

// GET /ground-summary — { districts: { <name>: { report_count, ... } } }
export function getGroundSummary(district) {
  const path = withQuery('/ground-summary', { district })
  return getJson(ENDPOINTS.damageApi, path)
}

// Full URL for GET /ground-reports/{id}/photo (image/jpeg). Not a fetch.
export function groundPhotoUrl(id) {
  return `${ENDPOINTS.damageApi}/ground-reports/${encodeURIComponent(id)}/photo`
}
