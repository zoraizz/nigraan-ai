import PageContainer from '../components/layout/PageContainer.jsx'
import DistrictCard from '../components/DistrictCard.jsx'
import HazardIcon from '../components/HazardIcon.jsx'
import { DISTRICTS, HAZARD_TYPES } from '../config/districts.js'

// Districts monitored per hazard type (coverage strip readout).
const HAZARD_COUNTS = HAZARD_TYPES.map((hazard) => ({
  hazard,
  count: DISTRICTS.filter((district) => district.hazards.includes(hazard)).length,
}))

// National overview — hazard coverage strip + district tiles. Live risk
// levels and aid rankings land on the Risk Map and Aid Priority pages;
// district tiles carry a neutral stripe until per-district risk is wired in.
export default function Overview() {
  return (
    <PageContainer
      title="Overview"
      lead={`Hazard monitoring across the ${DISTRICTS.length} districts covered by Risk Flag. Live risk assessments and aid rankings are on the Risk Map and Aid Priority pages.`}
    >
      <section
        className="panel mb-5 flex flex-wrap items-center gap-x-7 gap-y-3 px-4 py-3.5"
        aria-label="Hazard coverage"
      >
        <span className="text-sm font-medium text-muted">Hazard coverage</span>
        {HAZARD_COUNTS.map(({ hazard, count }) => (
          <span key={hazard} className="flex items-center gap-2">
            <HazardIcon hazard={hazard} />
            <span
              className="data text-base font-semibold text-text"
              title={`${count} of ${DISTRICTS.length} districts`}
            >
              {count}
            </span>
          </span>
        ))}
      </section>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {DISTRICTS.map((district) => (
          <DistrictCard key={district.name} district={district} />
        ))}
      </div>
    </PageContainer>
  )
}
