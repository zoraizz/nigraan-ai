import { useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import PriorityTable from '../components/PriorityTable.jsx'
import ScoringExplainer from '../components/ScoringExplainer.jsx'
import { useAidPriority } from '../hooks/useAidPriority.js'

// Demo scenario across real Nigraan districts — mixes both damage modes
// (damage_breakdown aggregation and single-tile overall_damage_level) so the
// ranking, the photo-count normalization, and the low-coverage warnings are
// all visible. A later iteration will assemble this payload live from
// Risk Flag + Damage Checker results.
const DEMO_PAYLOAD = [
  { district: 'Hunza', hazard_type: 'glof', risk_level: 'high',
    overall_damage_level: 'destroyed', confidence: 0.64 },
  { district: 'Rajanpur', hazard_type: 'flood', risk_level: 'high',
    damage_breakdown: { none: 40, partial: 25, destroyed: 35 } },
  { district: 'Mansehra', hazard_type: 'landslide', risk_level: 'high',
    overall_damage_level: 'partial', confidence: 0.71 },
  { district: 'Chitral', hazard_type: 'glof', risk_level: 'medium',
    damage_breakdown: { none: 15, partial: 5, destroyed: 5 }, tile_count: 30 },
  { district: 'Tharparkar', hazard_type: 'drought', risk_level: 'high',
    overall_damage_level: 'none', confidence: 0.83 },
  { district: 'Dadu', hazard_type: 'flood', risk_level: 'low',
    damage_breakdown: { none: 80, partial: 15, destroyed: 5 } },
]

export default function AidPriority() {
  const [submitted, setSubmitted] = useState(false)
  const { ranking, scoring, loading, error, refetch } = useAidPriority(
    submitted ? DEMO_PAYLOAD : [],
  )

  return (
    <PageContainer
      title="Aid Priority"
      lead="Districts ranked by aid urgency: 0.4 × risk + 0.6 × damage. The demo scenario mixes aggregated tile breakdowns with single-photo assessments; low-coverage warnings flag ranks that rest on very few tiles."
    >
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setSubmitted(true)}
          disabled={submitted}
          className="btn btn-primary"
        >
          {submitted ? 'Ranking loaded' : 'Run demo ranking'}
        </button>
        {submitted ? (
          <button
            type="button"
            onClick={refetch}
            disabled={loading}
            className="btn"
          >
            Re-fetch
          </button>
        ) : null}

        <details className="ml-auto max-w-md text-xs">
          <summary className="cursor-pointer text-muted hover:text-text">
            Request payload (demo scenario)
          </summary>
          <pre className="data well mt-2 max-h-72 overflow-auto p-3 text-xs leading-relaxed text-text">
            {JSON.stringify({ districts: DEMO_PAYLOAD }, null, 2)}
          </pre>
        </details>
      </div>

      {loading ? (
        <div className="panel px-4 py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Ranking districts…</p>
        </div>
      ) : error ? (
        <div className="alert-error p-4 text-sm">
          <p className="font-semibold">Aid Priority request failed</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-2 text-xs">
            Is the service running on http://127.0.0.1:8002? See
            dashboard/INTEGRATION.md.
          </p>
        </div>
      ) : (
        <PriorityTable rows={ranking} />
      )}

      <div className="mt-5">
        <ScoringExplainer scoring={scoring} />
      </div>
    </PageContainer>
  )
}
