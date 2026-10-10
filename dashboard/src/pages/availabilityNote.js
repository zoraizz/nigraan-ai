// Risk Map banner for partial weather. Wording matches
// risk-flag/weather_bundle.py availability_note. Flags are unchanged:
// weather_unavailable still means a critical hazard input is missing.

export const STATIC_ONLY_BANNER =
  'Live weather data was unavailable — risk assessment is based on static NDMA hazard context only.'

export const PARTIAL_BANNER =
  'Some required weather data is unavailable. This assessment uses the available weather and static NDMA hazard context.'

export const DROUGHT_HISTORY_BANNER =
  'Historical rainfall is unavailable, so this drought assessment is limited. It uses the available forecast and static NDMA hazard context.'

const USABLE_KEYS = [
  'rainfall_forecast_mm',
  'rainfall_30d_mm',
  'rainfall_90d_mm',
  'temperature_max_c_3d',
  'temperature_min_c_3d',
  'precip_probability_max_pct_3d',
  'wind_speed_max_kmh_3d',
  'wind_gust_max_kmh_3d',
  'humidity_mean_pct_3d',
  'soil_moisture_0_1cm_m3m3',
  'snowfall_cm_3d',
  'snow_depth_cm',
  'river_discharge_max_m3s_3d',
]

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readMetric(data, key) {
  if (!data || typeof data !== 'object') return null
  const metrics = data.weather_metrics
  if (metrics && typeof metrics === 'object') {
    const nested = finiteNumber(metrics[key])
    if (nested !== null) return nested
  }
  return finiteNumber(data[key])
}

export function availabilityBanner(data) {
  if (!data || typeof data !== 'object') return null
  if (data.risk_level === 'unknown') return null
  const weatherFlag = data.weather_unavailable === true
  const rainFlag = data.rainfall_unavailable === true
  if (!weatherFlag && !rainFlag) return null

  const hazards = Array.isArray(data.hazard_types) ? data.hazard_types : []
  const historyMissing =
    hazards.includes('drought') &&
    readMetric(data, 'temperature_max_c_3d') !== null &&
    (readMetric(data, 'rainfall_30d_mm') === null ||
      readMetric(data, 'rainfall_90d_mm') === null)
  if (historyMissing) return DROUGHT_HISTORY_BANNER

  const usable = USABLE_KEYS.some((key) => readMetric(data, key) !== null)
  return usable ? PARTIAL_BANNER : STATIC_ONLY_BANNER
}
