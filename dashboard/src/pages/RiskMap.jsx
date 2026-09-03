import { useState, useEffect } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import HazardIcon from '../components/HazardIcon.jsx'
import { useRiskData } from '../hooks/useRiskData.js'
import { DISTRICTS, DISTRICT_NAMES } from '../config/districts.js'

const RAINFALL_ROWS = [
  ['rainfall_forecast_mm', '3-day forecast'],
  ['rainfall_30d_mm', 'Last 30 days'],
  ['rainfall_90d_mm', 'Last 90 days'],
]

const LOADING_MESSAGES = [
  'Analyzing rainfall patterns…',
  'Cross-referencing NDMA hazard history…',
  'Consulting Gemini for risk assessment…',
  'Comparing against historical flood patterns…',
  'Synthesizing multi-signal risk score…',
]

// District risk view — live Risk Flag data for the selected district.
export default function RiskMap() {
  const [district, setDistrict] = useState(DISTRICT_NAMES[0])
  const { data, loading, error, refetch, elapsed } = useRiskData(district)
  const [msgIdx, setMsgIdx] = useState(0)

  // Rotate the status message every 25 s while loading; reset on district change.
  useEffect(() => {
    if (!loading) { setMsgIdx(0); return undefined }
    const id = setInterval(
      () => setMsgIdx((i) => (i + 1) % LOADING_MESSAGES.length),
      25_000,
    )
    return () => clearInterval(id)
  }, [loading, district])

  const selected = DISTRICTS.find((entry) => entry.name === district)
  const coords = selected?.coords

  return (
    <PageContainer
      title="District Risk"
      lead="Select a district to fetch its live risk assessment from Risk Flag. Weather data is fetched server-side; requests can take a few minutes."
    >
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* District list */}
        <div className="panel overflow-hidden">
          <ul className="divide-y divide-line">
            {DISTRICTS.map((entry) => (
              <li key={entry.name}>
                <button
                  type="button"
                  onClick={() => setDistrict(entry.name)}
                  aria-current={entry.name === district ? 'true' : undefined}
                  className={`select-row ${entry.name === district ? 'select-row-active' : ''}`}
                >
                  <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                    <span className="text-sm font-medium text-text">{entry.name}</span>
                    <span className="text-xs text-muted">{entry.province}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {entry.hazards.map((hazard) => (
                      <HazardIcon key={hazard} hazard={hazard} />
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Live risk panel */}
        <div className="panel h-fit p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="font-heading text-xl font-bold tracking-tight text-text">
                {district}
              </h3>
              {coords ? (
                <p className="data mt-0.5 text-xs text-muted">
                  {coords[0].toFixed(4)}° N, {coords[1].toFixed(4)}° E
                </p>
              ) : null}
            </div>
            {data ? <RiskBadge level={data.risk_level} /> : null}
          </div>

          {loading ? (
            <div className="py-10 text-center">
              <div className="spinner mx-auto mb-4" />
              <p className="text-sm font-medium text-text">{LOADING_MESSAGES[msgIdx]}</p>
              <p className="data mt-2 text-xs text-muted">
                elapsed {elapsed}s · Open-Meteo + Gemini can take up to 3 minutes
              </p>
            </div>
          ) : error ? (
            <div className="alert-error p-4 text-sm">
              <p className="font-semibold">Risk Flag request failed</p>
              <p className="mt-1">{error.message}</p>
              <p className="mt-2 text-xs">
                Is the service running on http://127.0.0.1:8000? See
                dashboard/INTEGRATION.md.
              </p>
              <button type="button" onClick={refetch} className="btn mt-3">
                Retry
              </button>
            </div>
          ) : data ? (
            <div>
              {data.cached ? (
                <p className="alert-ok mb-4 px-3 py-1.5 text-xs">
                  Returned from server cache (pre-warmed, no Gemini call)
                </p>
              ) : null}
              {data.hazard_types?.length > 0 ? (
                <div className="mb-4 flex flex-wrap gap-1.5">
                  {data.hazard_types.map((hazard) => (
                    <HazardIcon key={hazard} hazard={hazard} />
                  ))}
                </div>
              ) : null}

              <dl className="mb-4 space-y-1.5 text-sm">
                {RAINFALL_ROWS.map(([field, label]) =>
                  data[field] != null ? (
                    <div
                      key={field}
                      className="flex items-baseline justify-between gap-4 border-b border-line pb-1.5"
                    >
                      <dt className="text-muted">{label}</dt>
                      <dd className="data text-text">
                        {Number.isFinite(data[field])
                          ? data[field].toFixed(1)
                          : data[field]}{' '}
                        mm
                      </dd>
                    </div>
                  ) : null,
                )}
              </dl>

              <p className="well p-3 text-sm leading-relaxed text-text">{data.reason}</p>

              <button type="button" onClick={refetch} className="btn mt-4">
                Refresh
              </button>
            </div>
          ) : (
            <p className="py-10 text-center text-sm text-muted">No data yet.</p>
          )}
        </div>
      </div>
    </PageContainer>
  )
}
