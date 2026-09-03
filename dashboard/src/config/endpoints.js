// Base URLs for the three backend services.
// Values come from Vite env vars (see .env / .env.example) — Vite only
// exposes variables prefixed with VITE_. Defaults match the conventional
// local ports: risk-flag :8000, damage-checker :8001, aid-priority :8002.

const trimTrailingSlash = (url) => url.replace(/\/+$/, '')

export const ENDPOINTS = {
  riskApi: trimTrailingSlash(import.meta.env.VITE_RISK_API_URL || 'http://127.0.0.1:8000'),
  damageApi: trimTrailingSlash(import.meta.env.VITE_DAMAGE_API_URL || 'http://127.0.0.1:8001'),
  priorityApi: trimTrailingSlash(import.meta.env.VITE_PRIORITY_API_URL || 'http://127.0.0.1:8002'),
}
