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
    <PageContainer title="Aid Priority">
      <p className="mb-6 text-sm text-slate-500">
        Districts ranked by aid urgency — 0.4 × risk + 0.6 × damage. The demo
        scenario mixes aggregated tile breakdowns with single-photo
        assessments; low-coverage warnings flag ranks that rest on very few
        tiles.
      </p>

      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setSubmitted(true)}
          disabled={submitted}
          className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {submitted ? 'Ranking loaded' : 'Run demo ranking'}
        </button>
        {submitted ? (
          <button
            type="button"
            onClick={refetch}
            disabled={loading}
            className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Re-fetch
          </button>
        ) : null}

        <details className="ml-auto max-w-md">
          <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
            Request payload (demo scenario)
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
            {JSON.stringify({ districts: DEMO_PAYLOAD }, null, 2)}
          </pre>
        </details>
      </div>

      {loading ? (
        <p className="py-8 text-center text-sm text-slate-400">
          Ranking districts…
        </p>
      ) : error ? (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">Aid Priority request failed</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-2 text-xs">
            Is the service running on {`http://127.0.0.1:8002`}? See
            dashboard/INTEGRATION.md.
          </p>
        </div>
      ) : (
        <PriorityTable rows={ranking} />
      )}

      <div className="mt-6">
        <ScoringExplainer scoring={scoring} />
      </div>
    </PageContainer>
  )
}
