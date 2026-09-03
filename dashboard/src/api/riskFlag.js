// Risk Flag service (port 8000) — per-district risk levels.
import { ENDPOINTS } from '../config/endpoints.js'
import { postJson } from './client.js'

// POST /predict-risk
// NOTE: the server's RiskRequest model accepts ONLY { district } — rainfall
// is fetched server-side from Open-Meteo. (API_CONTRACT.md still lists
// rainfall_forecast_mm as a request field; the server ignores extra fields.)
// Response: { district, hazard_types, rainfall_forecast_mm, rainfall_30d_mm,
//             rainfall_90d_mm, risk_level: 'low'|'medium'|'high'|'unknown', reason }
export function predictRisk(district) {
  return postJson(ENDPOINTS.riskApi, '/predict-risk', { district })
}
