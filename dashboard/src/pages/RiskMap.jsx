import PageContainer from '../components/layout/PageContainer.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import HazardIcon from '../components/HazardIcon.jsx'
import { DISTRICTS } from '../config/districts.js'

// District risk view placeholder.
// TODO: fetch per-district risk from Risk Flag (useRiskData) and lay it out
// geographically — coords are already in config/districts.js.
export default function RiskMap() {
  return (
    <PageContainer title="District Risk">
      <p className="mb-6 text-sm text-slate-500">
        Placeholder — risk levels below are dummy values until Risk Flag
        integration lands.
      </p>
      <ul className="space-y-2">
        {DISTRICTS.map((district) => (
          <li
            key={district.name}
            className="flex items-center justify-between rounded border border-slate-200 bg-white px-4 py-3"
          >
            <div>
              <span className="font-medium text-slate-800">{district.name}</span>
              <span className="ml-2 text-xs text-slate-400">{district.province}</span>
            </div>
            <div className="flex items-center gap-3">
              {district.hazards.map((hazard) => (
                <HazardIcon key={hazard} hazard={hazard} />
              ))}
              <RiskBadge level="unknown" />
            </div>
          </li>
        ))}
      </ul>
    </PageContainer>
  )
}
