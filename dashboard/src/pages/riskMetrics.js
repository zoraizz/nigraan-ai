// Compact rows for the Risk Map weather panel.
// Nulls are omitted. Snowfall and snow depth at 0 are hidden outside
// GLOF/avalanche districts, where a zero is itself a signal.
// Hazard-relevant rows are listed first.

const METRICS = [
  {
    key: 'temperature_max_c_3d',
    label: 'Max temp',
    unit: '°C',
    digits: 1,
    relevant: ['drought', 'glof', 'avalanche'],
  },
  {
    key: 'temperature_min_c_3d',
    label: 'Min temp',
    unit: '°C',
    digits: 1,
    relevant: ['glof', 'avalanche'],
  },
  {
    key: 'rainfall_forecast_mm',
    label: 'Rain, 3-day',
    unit: 'mm',
    digits: 1,
    relevant: ['flood', 'landslide'],
    legacy: true,
  },
  {
    key: 'precip_probability_max_pct_3d',
    label: 'Precip probability',
    unit: '%',
    digits: 0,
    relevant: ['flood'],
  },
  {
    key: 'rainfall_30d_mm',
    label: 'Rain, 30-day',
    unit: 'mm',
    digits: 1,
    relevant: ['drought'],
    legacy: true,
  },
  {
    key: 'rainfall_90d_mm',
    label: 'Rain, 90-day',
    unit: 'mm',
    digits: 1,
    relevant: ['drought'],
    legacy: true,
  },
  {
    key: 'humidity_mean_pct_3d',
    label: 'Humidity',
    unit: '%',
    digits: 0,
    relevant: ['drought'],
  },
  {
    key: 'soil_moisture_0_1cm_m3m3',
    label: 'Soil moisture, 0–1 cm',
    unit: 'm³/m³',
    digits: 3,
    relevant: ['drought', 'landslide'],
  },
  {
    key: 'wind_speed_max_kmh_3d',
    label: 'Wind max',
    unit: 'km/h',
    digits: 1,
    relevant: ['flood', 'landslide', 'glof', 'avalanche'],
  },
  {
    key: 'wind_gust_max_kmh_3d',
    label: 'Wind gust',
    unit: 'km/h',
    digits: 1,
    relevant: ['flood', 'landslide', 'glof', 'avalanche'],
  },
  {
    key: 'snowfall_cm_3d',
    label: 'Snowfall, 3-day',
    unit: 'cm',
    digits: 1,
    relevant: ['glof', 'avalanche'],
    snow: true,
  },
  {
    key: 'snow_depth_cm',
    label: 'Snow depth',
    unit: 'cm',
    digits: 1,
    relevant: ['glof', 'avalanche'],
    snow: true,
  },
  {
    key: 'river_discharge_max_m3s_3d',
    label: 'River discharge',
    unit: 'm³/s',
    digits: 1,
    relevant: ['flood'],
  },
]

function readValue(data, def) {
  const nested = data?.weather_metrics?.[def.key]
  if (nested != null && Number.isFinite(Number(nested))) return Number(nested)
  if (def.legacy && data?.[def.key] != null && Number.isFinite(Number(data[def.key]))) {
    return Number(data[def.key])
  }
  return null
}

export function buildRiskMetricRows(data) {
  const hazards = new Set(data?.hazard_types || [])
  const snowDistrict = hazards.has('glof') || hazards.has('avalanche')
  const rows = []

  for (const def of METRICS) {
    const value = readValue(data, def)
    if (value == null) continue
    if (def.snow && !snowDistrict && value === 0) continue
    rows.push({
      key: def.key,
      label: def.label,
      unit: def.unit,
      digits: def.digits,
      value,
      snow: Boolean(def.snow),
      discharge: def.key === 'river_discharge_max_m3s_3d',
      relevant: def.relevant.some((hazard) => hazards.has(hazard)),
    })
  }

  const relevant = rows.filter((row) => row.relevant)
  const other = rows.filter((row) => !row.relevant)
  return [...relevant, ...other]
}

export function formatMetricValue(value, digits) {
  return Number(value).toFixed(digits)
}
