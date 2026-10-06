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

  let response
  try {
    response = await fetch(url, options)
  } catch (err) {
    // fetch only rejects on network-level failures (server down, CORS, DNS)
    throw new ApiError(`Network error contacting ${url}: ${err.message}`, 0, null)
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

export function getJson(baseUrl, path) {
  return request(baseUrl, path, { method: 'GET' })
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
