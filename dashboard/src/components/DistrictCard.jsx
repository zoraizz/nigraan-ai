import HazardIcon from './HazardIcon.jsx'
import RiskBadge, { RISK_STRIPE } from './RiskBadge.jsx'

// Compact district tile for the Overview page. The left edge stripe carries
// the risk level color; it stays neutral gray until live risk data is wired
// in (riskLevel defaults to 'unknown').
export default function DistrictCard({ district, riskLevel = 'unknown' }) {
  const stripe = RISK_STRIPE[riskLevel] || RISK_STRIPE.unknown
  return (
    <div className="panel stripe-left p-4" style={{ '--stripe': stripe }}>
      <div className="mb-1 flex items-start justify-between gap-2">
        <h3 className="font-heading text-[15px] font-semibold leading-snug text-text">
          {district.name}
        </h3>
        <RiskBadge level={riskLevel} />
      </div>
      <p className="mb-3 text-xs text-muted">{district.province}</p>
      <div className="flex flex-wrap gap-1.5">
        {district.hazards.map((hazard) => (
          <HazardIcon key={hazard} hazard={hazard} />
        ))}
      </div>
    </div>
  )
}
