import PageContainer from '../components/layout/PageContainer.jsx'
import PriorityTable from '../components/PriorityTable.jsx'
import ScoringExplainer from '../components/ScoringExplainer.jsx'
import { useAidPriority } from '../hooks/useAidPriority.js'
import { useLiveAssessment } from '../hooks/useLiveAssessment.js'
import { SAMPLE_PAIRING, hazardTypeFor } from '../config/samplePairing.js'

const statusClass = (status) => {
  if (status === 'ok') return 'text-ok-bright'
  if (status === 'error') return 'text-risk-high-bright'
  return 'text-muted'
}

export default function AidPriority() {
  const live = useLiveAssessment()
  const { ranking, scoring, loading, error, refetch } = useAidPriority(
    live.payload ?? [],
  )

  const running = live.phase === 'assembling' || loading

  return (
    <PageContainer
      title="Aid Priority"
      lead="Districts ranked by aid urgency: 0.4 × risk + 0.6 × damage. Running the ranking calls Risk Flag (/predict-risk, Gemini-backed) and Damage Checker (/classify-damage) live for five districts, then ranks them via /rank-priority."
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={live.run}
          disabled={running}
          className="btn btn-primary"
        >
          {live.phase === 'idle' ? 'Run live ranking' : 'Re-run live ranking'}
        </button>
        {live.payload ? (
          <button
            type="button"
            onClick={refetch}
            disabled={running}
            className="btn"
          >
            Re-post same payload
          </button>
        ) : null}

        <details className="ml-auto max-w-md text-xs">
          <summary className="cursor-pointer text-muted hover:text-text">
            Request payload (assembled live)
          </summary>
          {live.payload ? (
            <pre className="data well mt-2 max-h-72 overflow-auto p-3 text-xs leading-relaxed text-text">
              {JSON.stringify({ districts: live.payload }, null, 2)}
            </pre>
          ) : (
            <p className="mt-2 leading-relaxed text-muted">
              The payload assembles when the ranking runs: risk levels come
              from POST /predict-risk and damage levels from POST
              /classify-damage on the paired sample tiles.
            </p>
          )}
        </details>
      </div>

      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-muted">
        Damage assessment uses real classified sample imagery
        (damage-checker/sample-images/), illustratively paired with these
        districts, not a live satellite feed. Risk levels are live Risk Flag
        assessments and the ranking is computed live by the Aid Priority
        service.
      </p>

      <details className="mb-5 max-w-3xl text-xs">
        <summary className="cursor-pointer text-muted hover:text-text">
          District and sample tile pairing (illustrative)
        </summary>
        <ul className="mt-2 space-y-1 leading-relaxed text-muted">
          {SAMPLE_PAIRING.map((entry) => (
            <li key={entry.district}>
              <span className="text-text">{entry.district}</span>{' '}
              ({hazardTypeFor(entry.district)}):{' '}
              <span className="data">{entry.tile}</span>, {entry.tileSource}
            </li>
          ))}
        </ul>
      </details>

      {live.phase === 'assembling' ? (
        <div className="panel px-4 py-8 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">
            Assessing {SAMPLE_PAIRING.length} districts, Risk Flag (Gemini) and
            Damage Checker <span className="data">{live.elapsed}s</span>
          </p>
          <p className="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-muted">
            A cold server cache makes each district take minutes while Gemini
            reasons about it; the server caches results for 15 minutes.
          </p>
          <ul className="mx-auto mt-4 inline-block space-y-1 text-left text-xs">
            {live.progress.map((row) => (
              <li key={row.district} className="flex items-baseline gap-3">
                <span className="w-24 text-text">{row.district}</span>
                <span className={`w-28 ${statusClass(row.risk)}`}>
                  risk {row.risk === 'ok' ? row.risk_level : row.risk}
                </span>
                <span className={`w-40 ${statusClass(row.damage)}`}>
                  damage{' '}
                  {row.damage === 'ok'
                    ? `${row.damage_level} (${(row.confidence * 100).toFixed(1)}%)`
                    : row.damage}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : live.error ? (
        <div className="alert-error p-4 text-sm">
          <p className="font-semibold">Live assessment failed</p>
          <p className="mt-1">{live.error.message}</p>
          <p className="mt-2 text-xs">
            Are the services running (Risk Flag :8000, Damage Checker :8001,
            Aid Priority :8002)? See dashboard/INTEGRATION.md.
          </p>
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
      ) : loading ? (
        <div className="panel px-4 py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Ranking districts…</p>
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
