// Shared fetch wrapper used by every api/* module.
// - Base URLs come from ../config/endpoints.js (env-var driven, one per service)
// - Non-2xx responses raise ApiError carrying the backend's unified error body
//   ({ "error": { "code": ..., "message": ... } }) when present; FastAPI's
//   standard 422 "detail" format is handled too
// - Bodies are parsed as JSON when possible; empty bodies resolve to null

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
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
    const message =
      (body && body.error && body.error.message) ||
      (Array.isArray(body && body.detail)
        ? body.detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
        : body && body.detail) ||
      `Request failed with status ${response.status}`
    throw new ApiError(message, response.status, body)
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
