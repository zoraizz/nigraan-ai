// Risk Flag's risk_level values: low | medium | high | unknown.
// Flat pill in the risk token colors — no gradient, no shadow.
// RISK_STRIPE maps levels to the token CSS vars for left-edge stripes
// (DistrictCard, PriorityTable rows, DamageResultCard).
export const RISK_STRIPE = {
  low: 'var(--color-risk-low)',
  medium: 'var(--color-risk-medium)',
  high: 'var(--color-risk-high)',
  unknown: 'var(--color-risk-unknown)',
}

const LEVEL_CLASS = {
  low: 'risk-low',
  medium: 'risk-medium',
  high: 'risk-high',
  unknown: 'risk-unknown',
}

export default function RiskBadge({ level = 'unknown' }) {
  const cls = LEVEL_CLASS[level] || LEVEL_CLASS.unknown
  return (
    <span className={`risk-badge ${cls}`}>
      <span className="risk-dot" aria-hidden="true" />
      {level}
    </span>
  )
}
