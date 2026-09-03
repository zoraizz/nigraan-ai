import HazardIcon from './HazardIcon.jsx'
import RiskBadge from './RiskBadge.jsx'

// Compact district tile for the Overview page.
// `riskLevel` stays 'unknown' until live risk data is wired in.
export default function DistrictCard({ district, riskLevel = 'unknown' }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold text-slate-800">{district.name}</h3>
        <RiskBadge level={riskLevel} />
      </div>
      <p className="mb-2 text-xs text-slate-400">{district.province}</p>
      <div className="flex flex-wrap gap-2">
        {district.hazards.map((hazard) => (
          <HazardIcon key={hazard} hazard={hazard} />
        ))}
      </div>
    </div>
  )
}
