export const SCENES = ['flooded_street', 'flooded_farmland', 'collapsed_house', 'damaged_building', 'damaged_road', 'broken_bridge', 'landslide', 'debris', 'relief_camp', 'other_disaster']
export const NEEDS = ['rescue', 'shelter', 'medical', 'food_water', 'road_clearance']
export const DEPTHS = ['none', 'ankle', 'knee', 'waist', 'chest', 'above_head']
export const words = (value) => String(value ?? 'unknown').replaceAll('_', ' ')
// Uploads are field_worker or officer. citizen and rescue_team are only here
// so older stored reports still get a label; nothing offers them.
export const ROLES = { field_worker: 'Field worker', officer: 'Officer', citizen: 'Citizen', rescue_team: 'Rescue team' }
export const LEVELS = {
  none: 'text-risk-low-bright border-risk-low',
  partial: 'text-risk-medium-bright border-risk-medium',
  destroyed: 'text-risk-high-bright border-risk-high',
}
// Irrelevant route: shown instead of the backend's satellite OOD message.
export const NOT_DISASTER_MESSAGE = "This doesn't look like a disaster photo. Please send a photo of flood or damage taken on the ground."
export const REJECTION_REASONS = {
  vlm_irrelevant: 'No disaster or damage was found in the photo.',
  vlm_aerial: 'This looks like an aerial or satellite image but did not match our satellite model.',
  vlm_low_confidence: 'The photo was too unclear to read with confidence.',
  vlm_unavailable: 'The photo reader is unavailable right now, please try again in a minute.',
}
export const SATELLITE_NOTE = 'Recognised as a satellite image, so it was checked by the satellite damage model.'
