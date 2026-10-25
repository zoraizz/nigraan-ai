// Ground Photo Intake on the Damage Checker service (port 8001).
// POST /intake, GET /ground-reports, GET /ground-summary, PATCH .../review,
// DELETE /ground-reports/{id}.
// Base URL is ENDPOINTS.damageApi. Satellite classify routes are not called here.
//
// The /ground-reports routes need the shared officer PIN in X-Officer-Key
// (the photo URL carries it as ?officer_key=, since <img src> cannot send
// headers). AuthProvider writes the PIN here with setOfficerPin. A 401 that
// was sent with the current PIN tells onOfficerUnauthorized listeners, so the
// provider can drop back to field worker mode. Demo-grade, not real accounts.
import { ENDPOINTS } from '../config/endpoints.js'
import { ApiError, apiErrorMessage, getJson, postForm } from './client.js'

let officerPin = null
const unauthorizedListeners = new Set()

export function setOfficerPin(pin) {
  officerPin = pin || null
}

// Returns an unsubscribe function.
export function onOfficerUnauthorized(listener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function withQuery(path, params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `${path}?${text}` : path
}

// Same error shape as client.js's request, plus the officer header.
// pin defaults to the stored one; verifyOfficerPin passes a candidate PIN
// with notify: false so a wrong guess does not end a live session.
// form is a FormData body sent as-is (the browser sets its Content-Type).
async function officerRequest(path, { method = 'GET', payload, form, pin = officerPin, notify = true } = {}) {
  const url = `${ENDPOINTS.damageApi.replace(/\/+$/, '')}${path}`
  const headers = {}
  if (pin) headers['X-Officer-Key'] = pin
  if (payload !== undefined) headers['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: form ?? (payload === undefined ? undefined : JSON.stringify(payload)),
    })
  } catch (err) {
    console.warn(`Network error contacting ${url}: ${err.message}`)
    throw new ApiError('Could not reach the service. Service waking up, can take up to 60 seconds. Please try again.', 0, null)
  }

  let body = null
  const text = await response.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    if (response.status === 401 && notify && pin && pin === officerPin) {
      unauthorizedListeners.forEach((listener) => listener())
    }
    throw new ApiError(apiErrorMessage(body, response.status), response.status, body)
  }

  return body
}

// POST /intake — multipart field "image". Location and role are query params.
// Response is one of route satellite | ground | irrelevant. See API contract.
// Open to everyone, except reporterRole 'officer', which sends the stored
// officer PIN (the server answers 401 without it).
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
  if (reporterRole === 'officer') return officerRequest(path, { method: 'POST', form })
  return postForm(ENDPOINTS.damageApi, path, form)
}

// GET /ground-reports — JSON list. Default server list omits duplicates.
// filters: { district, status, urgent, include_duplicates }. Officer only.
export function listGroundReports(filters = {}) {
  const path = withQuery('/ground-reports', {
    district: filters.district,
    status: filters.status,
    urgent: filters.urgent,
    include_duplicates: filters.include_duplicates,
  })
  return officerRequest(path)
}

// Checks a candidate PIN with GET /ground-reports. Rejects with ApiError
// (status 401 for a wrong PIN) and never ends the current session.
export function verifyOfficerPin(pin) {
  return officerRequest('/ground-reports', { pin, notify: false })
}

export function getGroundReport(id) {
  return officerRequest(`/ground-reports/${encodeURIComponent(id)}`)
}

// PATCH /ground-reports/{id}/review
// body: { action, corrections?, note?, officer? }
export function reviewGroundReport(id, body) {
  return officerRequest(`/ground-reports/${encodeURIComponent(id)}/review`, {
    method: 'PATCH',
    payload: body,
  })
}

// DELETE /ground-reports/{id} — removes the report and its photo for good.
// Resolves to { deleted: id }. Reject is the way to keep a record instead.
export function deleteGroundReport(id) {
  return officerRequest(`/ground-reports/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// GET /ground-summary — { districts: { <name>: { report_count, ... } } }
// Open: aggregate counts only (Aid Priority reads it too).
export function getGroundSummary(district) {
  const path = withQuery('/ground-summary', { district })
  return getJson(ENDPOINTS.damageApi, path)
}

// Full URL for GET /ground-reports/{id}/photo (image/jpeg). Not a fetch.
// Carries the officer PIN as officer_key when one is set.
export function groundPhotoUrl(id) {
  const path = withQuery(`/ground-reports/${encodeURIComponent(id)}/photo`, {
    officer_key: officerPin,
  })
  return `${ENDPOINTS.damageApi}${path}`
}
