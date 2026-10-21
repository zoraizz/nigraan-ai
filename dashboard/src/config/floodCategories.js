// Flood categories for the River Flood Tracker.
// One list feeds the map strokes, the badges, and the legend.
// Order is the contract order: Normal is the lowest, Exceptionally High the highest.
// A reach uses the higher of its two end barrages; the API already resolves that,
// and these colours only display the category string the API sends.

export const FLOOD_CATEGORIES = [
  { key: 'Normal', label: 'Normal', color: '#3ddc84' },
  { key: 'Low Flood', label: 'Low Flood', color: '#b6d94a' },
  { key: 'Medium Flood', label: 'Medium Flood', color: '#e8b931' },
  { key: 'High Flood', label: 'High Flood', color: '#ff7a1a' },
  { key: 'Very High Flood', label: 'Very High Flood', color: '#ef4444' },
  { key: 'Exceptionally High Flood', label: 'Exceptionally High Flood', color: '#c026d3' },
]

const UNKNOWN = { key: 'Unknown', label: 'Unknown', color: '#6f8f7e' }

export function floodCategory(name) {
  if (!name) return UNKNOWN
  return FLOOD_CATEGORIES.find((item) => item.key === name) ?? {
    key: name,
    label: name,
    color: UNKNOWN.color,
  }
}
