import PageContainer from '../components/layout/PageContainer.jsx'
import DistrictCard from '../components/DistrictCard.jsx'
import { DISTRICTS } from '../config/districts.js'

// Landing page — summary view placeholder.
// TODO: aggregate Risk Flag risk levels and Aid Priority rankings into an
// at-a-glance national overview.
export default function Overview() {
  return (
    <PageContainer title="Overview">
      <p className="mb-6 text-sm text-slate-500">
        Placeholder — will summarize current risk levels and top aid priorities
        across all {DISTRICTS.length} districts.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {DISTRICTS.map((district) => (
          <DistrictCard key={district.name} district={district} />
        ))}
      </div>
    </PageContainer>
  )
}
