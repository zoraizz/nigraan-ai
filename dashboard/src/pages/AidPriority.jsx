import PageContainer from '../components/layout/PageContainer.jsx'
import PriorityTable from '../components/PriorityTable.jsx'
import ScoringExplainer from '../components/ScoringExplainer.jsx'

// Ranked priority list placeholder.
// TODO: wire useAidPriority to POST /rank-priority and render the response.
export default function AidPriority() {
  return (
    <PageContainer title="Aid Priority">
      <p className="mb-6 text-sm text-slate-500">
        Placeholder — districts ranked by aid urgency (risk + damage).
      </p>
      <PriorityTable rows={[]} />
      <div className="mt-6">
        <ScoringExplainer />
      </div>
    </PageContainer>
  )
}
