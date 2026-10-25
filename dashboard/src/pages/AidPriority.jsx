import { useEffect, useRef, useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import PriorityTable from '../components/PriorityTable.jsx'
import ScoringExplainer from '../components/ScoringExplainer.jsx'
import { useAidPriority } from '../hooks/useAidPriority.js'
import { useFloodEtas } from '../hooks/useFloodEtas.js'
import { useLiveAssessment } from '../hooks/useLiveAssessment.js'
import { formatReplayStamp } from '../components/flood/timeFormat.js'
import { SAMPLE_PAIRING, hazardTypeFor } from '../config/samplePairing.js'
import { useSceneDamage } from '../scene/SceneDamageProvider.jsx'
import { useServicesReady } from '../warmup/ServiceWarmup.jsx'

// Services the ranking cannot run without. Flood Tracker is optional: its
// ETAs have their own 5 s cap and the ranking runs without them.
const NEEDED_SERVICES = ['risk', 'damage', 'priority']

// Seconds into a run after which the cold-start note appears (free-tier
// services sleep when idle and take up to a minute to wake).
const WAKE_NOTE_AFTER_S = 8

const statusClass = (status) => {
  if (status === 'ok') return 'text-ok-bright'
  if (status === 'error') return 'text-risk-high-bright'
  return 'text-muted'
}

function sceneLabel(sceneDamage) {
  if (!sceneDamage) return 'illustrative sample image'
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

function formatRunTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function AidPriority() {
  const { sceneDamage, clearSceneDamage } = useSceneDamage()
  // ground: off by default; applies on the next live run
  const [includeGround, setIncludeGround] = useState(false)
  const live = useLiveAssessment(sceneDamage, { includeGround })
  // flood: wait for the ETA request (5 s cap) so the ranking posts once.
  const flood = useFloodEtas()
  const payload = flood.settled ? withFloodEtas(live.payload, flood.etas) : null
  const floodCount = payload ? payload.filter((entry) => 'flood_eta_hours' in entry).length : 0
  const { ranking, scoring, loading, error } = useAidPriority(
    payload ?? [],
  )
  const [lastRun, setLastRun] = useState(null)

  // Run the live ranking once, after the services it needs answered their
  // health check; the ref keeps StrictMode's double effect from a second run.
  const services = useServicesReady(NEEDED_SERVICES)
  const autoRan = useRef(false)
  const { run } = live
  useEffect(() => {
    if (autoRan.current || !services.ready) return
    autoRan.current = true
    run()
  }, [run, services.ready])
  const waiting = live.phase === 'idle' && !autoRan.current && !services.ready

  useEffect(() => {
    if (!loading && !error && ranking.length > 0) setLastRun(new Date())
  }, [ranking, loading, error])

  const handleClearScene = () => {
    clearSceneDamage()
    live.reset()
  }

  const running = live.phase === 'assembling' || loading

  return (
    <PageContainer
      title="Aid Priority"
      lead="Districts ranked for relief by 0.4 × risk + 0.6 × damage, using live Risk Flag levels and damage classifications."
    >
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => {
            autoRan.current = true
            live.run()
          }}
          disabled={running}
          className="btn btn-primary"
        >
          {running ? 'Ranking…' : 'Re-run'}
        </button>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={includeGround}
            onChange={(event) => setIncludeGround(event.target.checked)}
            disabled={running}
            className="accent-emerald-500"
          />
          Include ground reports
        </label>
        {live.groundError ? (
          <span className="text-xs text-muted" title={live.groundError}>
            Ground reports unavailable, ranked without them
          </span>
        ) : null}
        {lastRun ? (
          <span className="ml-auto text-xs text-muted">
            Last run <span className="data text-text">{formatRunTime(lastRun)}</span>
          </span>
        ) : null}
      </div>

      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-muted">
        Damage uses sample imagery paired illustratively with districts, not a live satellite feed.
      </p>

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

      {waiting && services.failed.length > 0 ? (
        <div className="alert-error p-4 text-sm">
          <p className="font-semibold">The ranking has not run</p>
          <p className="mt-1">
            {services.failed.join(', ')} did not answer within 90 seconds. Try Re-run.
          </p>
        </div>
      ) : waiting ? (
        <div className="panel px-4 py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Waking services: {services.pending.join(', ')}</p>
          <p className="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-muted">
            Service waking up, can take up to 60 seconds. The ranking starts on its own.
          </p>
        </div>
      ) : live.phase === 'assembling' ? (
        <div className="panel px-4 py-8 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">
            Assessing {live.progress.length} districts{' '}
            <span className="data">{live.elapsed}s</span>
          </p>
          {live.elapsed >= WAKE_NOTE_AFTER_S ? (
            <p className="mx-auto mt-1 max-w-xl text-xs leading-relaxed text-muted">
              Service waking up, can take up to 60 seconds. Without a recent
              result, a district can take longer while Risk Flag reasons about
              it (Gemini, then Grok, then a rule scorer).
            </p>
          ) : null}
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
          <p className="font-semibold">Could not assess the districts</p>
          <p className="mt-1">{live.error.message}</p>
          <p className="mt-2 text-xs">
            A service may be waking up, which can take up to 60 seconds. Try Re-run.
          </p>
        </div>
      ) : error ? (
        <div className="alert-error p-4 text-sm">
          <p className="font-semibold">Could not rank the districts</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-2 text-xs">
            The ranking service may be waking up, which can take up to 60 seconds. Try Re-run.
          </p>
        </div>
      ) : loading || live.phase === 'idle' || (live.phase === 'done' && !flood.settled) ? (
        <div className="panel px-4 py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Ranking districts…</p>
        </div>
      ) : (
        <PriorityTable rows={ranking} />
      )}

      <details className="mt-5 max-w-3xl text-xs">
        <summary className="cursor-pointer text-muted hover:text-text">
          Method and details
        </summary>
        <div className="mt-3 space-y-4">
          <ScoringExplainer scoring={scoring} rows={ranking} />

          <p className="leading-relaxed text-muted">
            Risk levels are live Risk Flag assessments, and the ranking is
            computed live by the Aid Priority service. Each sample image is
            real and is classified live, but which image stands in for which
            district is an illustrative choice. A district marked damage from
            uploaded scene uses that scene's tile counts instead. Risk Flag
            results are cached for 15 minutes.
          </p>

          {/* flood: shown only when the River Flood Tracker answered */}
          {flood.settled && !flood.error && Object.keys(flood.etas).length > 0 ? (
            <p className="leading-relaxed text-muted">
              Flood ETAs: River Flood Tracker 2022 replay at{' '}
              <span className="data text-text">{formatReplayStamp(flood.asOf)}</span>{' '}
              (the step last viewed on Flood Tracker). Modelled hours until the
              river peak reaches the district; districts with no ETA have none.
              {payload ? ` ${floodCount} of ${payload.length} ranked districts have water due.` : ''}
            </p>
          ) : null}

          <div>
            <p className="font-semibold text-text">District damage sources</p>
            <ul className="mt-1 space-y-1 leading-relaxed text-muted">
              {SAMPLE_PAIRING.map((entry) => {
                const fromScene = sceneDamage?.district === entry.district
                return (
                  <li key={entry.district}>
                    <span className="text-text">{entry.district}</span>{' '}
                    ({hazardTypeFor(entry.district)}):{' '}
                    {fromScene ? sceneLabel(sceneDamage) : `illustrative sample image, ${entry.tileSource}`}
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
          </div>

          <div>
            <p className="font-semibold text-text">Data sent for ranking</p>
            {payload ? (
              <pre className="data well mt-2 max-h-72 overflow-auto p-3 text-xs leading-relaxed text-text">
                {JSON.stringify({ districts: payload }, null, 2)}
              </pre>
            ) : (
              <p className="mt-1 leading-relaxed text-muted">
                Appears once the districts have been assessed.
              </p>
            )}
          </div>
        </div>
      </details>
    </PageContainer>
  )
}
