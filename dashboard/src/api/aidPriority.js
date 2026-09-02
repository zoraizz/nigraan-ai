// Aid Priority service (port 8002) — districts ranked by aid urgency.
import { ENDPOINTS } from '../config/endpoints.js'
import { postJson } from './client.js'

// POST /rank-priority
// districts: array of assessment objects — each needs district, hazard_type,
// risk_level (from /predict-risk) and exactly one damage field:
// damage_breakdown (aggregated /classify-damage tile counts) or
// overall_damage_level (single-tile mode). See API_CONTRACT.md for the
// full schema.
// Response: { ranked_districts: [...], scoring: { ... } }
export function rankPriority(districts) {
  return postJson(ENDPOINTS.priorityApi, '/rank-priority', { districts })
}
