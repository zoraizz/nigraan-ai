// Warm-up pings for the four backend services (GET only, no side effects).
// Free-tier Render instances sleep when idle; a GET wakes them, so the app
// pings all four on first load instead of on the first real request.
// risk-flag has no /health route: its GET / is its health check.
import { ENDPOINTS } from '../config/endpoints.js'
import { getJson } from './client.js'

export const SERVICES = [
  { key: 'risk', label: 'Risk Flag', baseUrl: ENDPOINTS.riskApi, path: '/' },
  { key: 'damage', label: 'Damage Checker', baseUrl: ENDPOINTS.damageApi, path: '/health' },
  { key: 'priority', label: 'Aid Priority', baseUrl: ENDPOINTS.priorityApi, path: '/health' },
  { key: 'flood', label: 'Flood Tracker', baseUrl: ENDPOINTS.floodApi, path: '/health' },
]

export function pingService(service, signal) {
  return getJson(service.baseUrl, service.path, { signal, quiet: true })
}
