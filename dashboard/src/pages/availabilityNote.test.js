import assert from 'node:assert/strict'
import test from 'node:test'

import { availabilityBanner } from './availabilityNote.js'

const droughtPartial = {
  district: 'Tharparkar',
  hazard_types: ['drought'],
  risk_level: 'high',
  weather_unavailable: true,
  rainfall_unavailable: true,
  rainfall_forecast_mm: 0,
  rainfall_30d_mm: null,
  rainfall_90d_mm: null,
  weather_metrics: {
    rainfall_forecast_mm: 0,
    rainfall_30d_mm: null,
    rainfall_90d_mm: null,
    temperature_max_c_3d: 36.7,
    humidity_mean_pct_3d: 60.7,
    soil_moisture_0_1cm_m3m3: 0.103,
  },
}

test('drought forecast does not claim a static-only assessment', () => {
  const banner = availabilityBanner(droughtPartial)
  assert.match(banner, /Historical rainfall is unavailable/)
  assert.match(banner, /drought assessment is limited/)
  assert.doesNotMatch(banner, /context only/)
})

test('complete outage is the only static-context banner', () => {
  const banner = availabilityBanner({
    hazard_types: ['drought'],
    weather_unavailable: true,
    rainfall_unavailable: true,
    weather_metrics: {},
  })
  assert.match(banner, /static NDMA hazard context only/)
})

test('other usable metrics stay a partial warning', () => {
  const banner = availabilityBanner({
    hazard_types: ['flood'],
    rainfall_unavailable: true,
    weather_unavailable: true,
    rainfall_forecast_mm: null,
    weather_metrics: { humidity_mean_pct_3d: 40 },
  })
  assert.match(banner, /Some required weather data is unavailable/)
  assert.doesNotMatch(banner, /context only/)
})

test('unknown districts and complete responses have no banner', () => {
  assert.equal(
    availabilityBanner({
      risk_level: 'unknown',
      weather_unavailable: true,
      rainfall_unavailable: true,
    }),
    null,
  )
  assert.equal(
    availabilityBanner({
      hazard_types: ['flood'],
      weather_unavailable: false,
      rainfall_unavailable: false,
      rainfall_forecast_mm: 12,
    }),
    null,
  )
  assert.equal(availabilityBanner(null), null)
})

test('legacy rainfall-only bodies stay safe', () => {
  assert.match(
    availabilityBanner({ rainfall_unavailable: true }),
    /static NDMA hazard context only/,
  )
  const partial = availabilityBanner({
    rainfall_unavailable: true,
    rainfall_forecast_mm: 4,
  })
  assert.match(partial, /available weather/)
  assert.doesNotMatch(partial, /context only/)
})
