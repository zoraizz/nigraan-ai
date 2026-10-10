// Base URLs for the three backend services.
// Values come from Vite env vars (see .env / .env.example) — Vite only
// exposes variables prefixed with VITE_. Defaults match the conventional
// local ports: risk-flag :8000, damage-checker :8001, aid-priority :8002.
// Damage Assessment uses damageApi. If nothing is listening there, the
// browser reports "Failed to fetch". Start damage-checker on :8001, or set
// VITE_DAMAGE_API_URL to https://nigraan-damage-checker.onrender.com and
// restart Vite. A Render cold start can take 30–60 s.

const trimTrailingSlash = (url) => url.replace(/\/+$/, '')

export const ENDPOINTS = {
  riskApi: trimTrailingSlash(import.meta.env.VITE_RISK_API_URL || 'http://127.0.0.1:8000'),
  damageApi: trimTrailingSlash(import.meta.env.VITE_DAMAGE_API_URL || 'http://127.0.0.1:8001'),
  priorityApi: trimTrailingSlash(import.meta.env.VITE_PRIORITY_API_URL || 'http://127.0.0.1:8002'),
}
