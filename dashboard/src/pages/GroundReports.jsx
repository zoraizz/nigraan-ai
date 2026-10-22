import PageContainer from '../components/layout/PageContainer.jsx'
import { ENDPOINTS } from '../config/endpoints.js'
import { useGroundReports } from '../hooks/useGroundReports.js'

function isUnreachable(error) {
  if (!error) return false
  if (error.status === 0) return true
  const message = String(error.message || '')
  return /network error|failed to fetch|networkerror/i.test(message)
}

function rawCount(value) {
  return Number.isFinite(value) ? String(value) : '—'
}

function Count({ label, value, pending }) {
  return (
    <p className="mt-3 text-sm text-muted">
      {label}{' '}
      <span className="data text-lg font-semibold text-text">
        {pending ? '—' : rawCount(value)}
      </span>
    </p>
  )
}

export default function GroundReports() {
  const { reports, summary, loading, error, refetch } = useGroundReports()
  const unreachable = isUnreachable(error)
  const pending = loading || Boolean(error)
  const list = Array.isArray(reports) ? reports : []
  const urgentCount = list.filter((report) => report && report.urgent === true).length
  const queueCount = list.filter((report) => report && report.status === 'unverified').length
  const districts = summary && summary.districts && typeof summary.districts === 'object'
    ? Object.entries(summary.districts)
    : []

  return (
    <PageContainer
      title="Ground Reports"
      lead="Ground-level disaster photos held by damage-checker. The numbers are report and photo counts from the current list and district summary."
    >
      {loading ? (
        <div className="panel mb-4 px-4 py-6 text-center">
          <div className="spinner mx-auto mb-3" />
          <p className="text-sm text-muted">Loading ground reports…</p>
        </div>
      ) : null}

      {unreachable ? (
        <div className="alert-error mb-4 p-4 text-sm" role="alert">
          <p className="font-semibold">damage-checker is not reachable</p>
          <p className="mt-1 text-xs">
            Damage Checker: <span className="data">{ENDPOINTS.damageApi}</span>
          </p>
          <button type="button" className="btn mt-3" onClick={refetch}>
            Try again
          </button>
        </div>
      ) : error ? (
        <div className="alert-error mb-4 p-4 text-sm" role="alert">
          <p className="font-semibold">Ground reports request failed</p>
          <p className="mt-1">{error.message}</p>
          <button type="button" className="btn mt-3" onClick={refetch}>
            Try again
          </button>
        </div>
      ) : null}

      <div className="space-y-4">
        <section className="panel p-4" aria-labelledby="ground-submit">
          <h3 id="ground-submit" className="text-sm font-semibold text-text">Submit a photo</h3>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">
            Photos submitted through POST /intake appear in the stored-report count.
          </p>
          <Count label="Stored reports" value={list.length} pending={pending} />
        </section>

        <section className="panel p-4" aria-labelledby="ground-urgent">
          <h3 id="ground-urgent" className="text-sm font-semibold text-text">Urgent</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Reports the service marked urgent. This count is display-only.
          </p>
          <Count label="Urgent reports" value={urgentCount} pending={pending} />
        </section>

        <section className="panel p-4" aria-labelledby="ground-queue">
          <h3 id="ground-queue" className="text-sm font-semibold text-text">Review queue</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Reports with status unverified, still waiting for an officer.
          </p>
          <Count label="Unverified reports" value={queueCount} pending={pending} />
        </section>

        <section className="panel p-4" aria-labelledby="ground-districts">
          <h3 id="ground-districts" className="text-sm font-semibold text-text">District ground picture</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Per-district report, photo, verified, and urgent-open counts from the ground summary.
          </p>
          <Count label="Districts" value={districts.length} pending={pending} />
          {!pending && districts.length > 0 ? (
            <ul className="mt-3 space-y-2 text-sm text-muted">
              {districts.map(([name, row]) => (
                <li key={name}>
                  <span className="text-text">{name}</span>
                  {': report_count '}
                  <span className="data">{rawCount(row?.report_count)}</span>
                  {', photo_count '}
                  <span className="data">{rawCount(row?.photo_count)}</span>
                  {', verified_count '}
                  <span className="data">{rawCount(row?.verified_count)}</span>
                  {', urgent_open '}
                  <span className="data">{rawCount(row?.urgent_open)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </PageContainer>
  )
}
