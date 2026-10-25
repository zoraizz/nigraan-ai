// Shared fetch wrapper used by every api/* module.
// - Base URLs come from ../config/endpoints.js (env-var driven, one per service)
// - Non-2xx responses raise ApiError. Message extraction covers Aid Priority's
//   { "error": { "code", "message" } }, Damage Checker's scene rejects
//   { "error": "<text that includes the env limit>", "code" }, and FastAPI's
//   422 "detail" format.
// - Bodies are parsed as JSON when possible; empty bodies resolve to null

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

// Damage Checker scene rejects use { "error": "string", "code": "..." }
// (the string already states the env-configured limit). Aid Priority uses
// { "error": { "code", "message" } }. FastAPI validation uses "detail".
export function apiErrorMessage(body, status) {
  if (body && typeof body.error === 'string' && body.error) {
    return body.error
  }
  if (body && body.error && typeof body.error.message === 'string' && body.error.message) {
    return body.error.message
  }
  if (Array.isArray(body && body.detail)) {
    return body.detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
  }
  if (body && typeof body.detail === 'string' && body.detail) {
    return body.detail
  }
  return `Request failed with status ${status}`
}

async function request(baseUrl, path, options = {}) {
  const url = `${baseUrl.replace(/\/+$/, '')}${path}`

  // quiet: skip the console warning (warm-up pings retry and fail by design)
  const { quiet = false, ...fetchOptions } = options
  let response
  try {
    response = await fetch(url, fetchOptions)
  } catch (err) {
    // fetch only rejects on network-level failures (server down, CORS, DNS)
    if (!quiet) console.warn(`Network error contacting ${url}: ${err.message}`)
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
    throw new ApiError(apiErrorMessage(body, response.status), response.status, body)
  }

  return body
}

// options: { signal, quiet } (both optional)
export function getJson(baseUrl, path, options = {}) {
  return request(baseUrl, path, { ...options, method: 'GET' })
}

export function postJson(baseUrl, path, payload) {
  return request(baseUrl, path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Multipart upload — the browser sets the Content-Type boundary automatically,
// so it must NOT be set manually.
export function postForm(baseUrl, path, formData) {
  return request(baseUrl, path, { method: 'POST', body: formData })
}

// JSON PATCH. Ground report review uses this; callers own the body shape.
export function patchJson(baseUrl, path, payload) {
  return request(baseUrl, path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
