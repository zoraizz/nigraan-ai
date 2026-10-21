import PageContainer from '../components/layout/PageContainer.jsx'
import PriorityTable from '../components/PriorityTable.jsx'
import ScoringExplainer from '../components/ScoringExplainer.jsx'
import { useAidPriority } from '../hooks/useAidPriority.js'
import { useFloodEtas } from '../hooks/useFloodEtas.js'
import { useLiveAssessment } from '../hooks/useLiveAssessment.js'
import { formatReplayStamp } from '../components/flood/timeFormat.js'
import { SAMPLE_PAIRING, hazardTypeFor } from '../config/samplePairing.js'
import { useSceneDamage } from '../scene/SceneDamageProvider.jsx'

const statusClass = (status) => {
  if (status === 'ok') return 'text-ok-bright'
  if (status === 'error') return 'text-risk-high-bright'
  return 'text-muted'
}

function sceneLabel(sceneDamage) {
  if (!sceneDamage) return 'illustrative sample tile'
  return sceneDamage.truncated
    ? 'damage from uploaded scene, partial scene'
    : 'damage from uploaded scene'
}

// flood: flood_eta_hours only for districts with a River Flood Tracker ETA.
// A negative ETA means the arrival window is already open; aid-priority
// takes hours >= 0, so it is sent as 0.
function withFloodEtas(payload, etas) {
  if (!payload) return null
  return payload.map((entry) => {
    const hours = etas[entry.district]
    if (!Number.isFinite(hours)) return entry
    return { ...entry, flood_eta_hours: Math.max(0, Math.round(hours * 10) / 10) }
  })
}

export default function AidPriority() {
  const { sceneDamage, clearSceneDamage } = useSceneDamage()
  const live = useLiveAssessment(sceneDamage)
  // flood: wait for the ETA request (5 s cap) so the ranking posts once.
  const flood = useFloodEtas()
  const payload = flood.settled ? withFloodEtas(live.payload, flood.etas) : null
  const floodCount = payload ? payload.filter((entry) => 'flood_eta_hours' in entry).length : 0
  const { ranking, scoring, loading, error, refetch } = useAidPriority(
    payload ?? [],
  )

  const handleClearScene = () => {
    clearSceneDamage()
    live.reset()
  }

  const running = live.phase === 'assembling' || loading

  return (
    <PageContainer
      title="Aid Priority"
      lead="Districts ranked by aid urgency: 0.4 × risk + 0.6 × damage. Running the ranking calls Risk Flag (/predict-risk, Gemini-backed) and Damage Checker live, then ranks them via /rank-priority. A stored scene replaces that district's sample tile."
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
          {payload ? (
            <pre className="data well mt-2 max-h-72 overflow-auto p-3 text-xs leading-relaxed text-text">
              {JSON.stringify({ districts: payload }, null, 2)}
            </pre>
          ) : (
            <p className="mt-2 leading-relaxed text-muted">
              The payload assembles when the ranking runs: risk levels come
              from POST /predict-risk. Damage comes from POST /classify-damage
              on the paired sample tiles, or from an uploaded scene when one
              is stored for that district.
            </p>
          )}
        </details>
      </div>

      {sceneDamage ? (
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
          <p>
            <span className="font-semibold text-text">{sceneDamage.district}</span>
            <span className="text-muted">: damage from uploaded scene</span>
          </p>
          {sceneDamage.truncated ? <span className="warn-chip">partial scene</span> : null}
          <button type="button" className="btn" onClick={handleClearScene}>
            Clear uploaded scene
          </button>
        </div>
      ) : null}

      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-muted">
        Damage assessment uses real classified sample imagery
        (damage-checker/sample-images/), illustratively paired with these
        districts, not a live satellite feed. A district marked damage from
        uploaded scene uses the stored tile counts instead. Risk levels are
        live Risk Flag assessments and the ranking is computed live by the
        Aid Priority service.
      </p>

      {/* flood: shown only when the River Flood Tracker answered */}
      {flood.settled && !flood.error && Object.keys(flood.etas).length > 0 ? (
        <p className="-mt-2 mb-4 max-w-3xl text-xs leading-relaxed text-muted">
          Flood ETAs: River Flood Tracker 2022 replay at{' '}
          <span className="data text-text">{formatReplayStamp(flood.asOf)}</span>{' '}
          (the step last viewed on Flood Tracker). Modelled hours until the
          river peak reaches the district; districts with no ETA send none.
          {payload ? ` ${floodCount} of ${payload.length} ranked districts have water due.` : ''}
        </p>
      ) : null}

      <details className="mb-5 max-w-3xl text-xs">
        <summary className="cursor-pointer text-muted hover:text-text">
          District damage sources
        </summary>
        <ul className="mt-2 space-y-1 leading-relaxed text-muted">
          {SAMPLE_PAIRING.map((entry) => {
            const fromScene = sceneDamage?.district === entry.district
            return (
              <li key={entry.district}>
                <span className="text-text">{entry.district}</span>{' '}
                ({hazardTypeFor(entry.district)}):{' '}
                {fromScene ? (
                  sceneLabel(sceneDamage)
                ) : (
                  <>
                    illustrative sample tile,{' '}
                    <span className="data">{entry.tile}</span>, {entry.tileSource}
                  </>
                )}
              </li>
            )
          })}
          {sceneDamage && !SAMPLE_PAIRING.some((entry) => entry.district === sceneDamage.district) ? (
            <li>
              <span className="text-text">{sceneDamage.district}</span>{' '}
              ({hazardTypeFor(sceneDamage.district)}): {sceneLabel(sceneDamage)}
            </li>
          ) : null}
        </ul>
      </details>

      {live.phase === 'assembling' ? (
        <div className="panel px-4 py-8 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">
            Assessing {live.progress.length} districts, Risk Flag (Gemini) and
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
                <span className={statusClass(row.damage)}>
                  {row.damage_source === 'scene' && row.damage === 'ok'
                    ? sceneLabel({ truncated: row.truncated })
                    : row.damage === 'ok'
                      ? `damage ${row.damage_level} (${(row.confidence * 100).toFixed(1)}%)`
                      : `damage ${row.damage}`}
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
