import { useState } from 'react'
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

// District risk view — live Risk Flag data for the selected district.
export default function RiskMap() {
  const [district, setDistrict] = useState(DISTRICT_NAMES[0])
  const { data, loading, error, refetch } = useRiskData(district)

  return (
    <PageContainer title="District Risk">
      <p className="mb-6 text-sm text-slate-500">
        Select a district to fetch its live risk assessment from Risk Flag
        (weather data is fetched server-side; requests can take a few minutes).
      </p>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* District list */}
        <ul className="space-y-1">
          {DISTRICTS.map((entry) => (
            <li key={entry.name}>
              <button
                type="button"
                onClick={() => setDistrict(entry.name)}
                className={`flex w-full items-center justify-between rounded border px-4 py-2 text-left text-sm ${
                  entry.name === district
                    ? 'border-slate-800 bg-slate-800 text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                <span>
                  <span className="font-medium">{entry.name}</span>
                  <span
                    className={`ml-2 text-xs ${
                      entry.name === district ? 'text-slate-300' : 'text-slate-400'
                    }`}
                  >
                    {entry.province}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  {entry.hazards.map((hazard) => (
                    <HazardIcon key={hazard} hazard={hazard} />
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {/* Live risk panel */}
        <div className="rounded border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-800">{district}</h3>
            {data ? <RiskBadge level={data.risk_level} /> : null}
          </div>

          {loading ? (
            <p className="py-8 text-center text-sm text-slate-400">
              Contacting Risk Flag… (Open-Meteo + Gemini can take a few minutes)
            </p>
          ) : error ? (
            <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium">Risk Flag request failed</p>
              <p className="mt-1">{error.message}</p>
              <p className="mt-2 text-xs">
                Is the service running on {`http://127.0.0.1:8000`}? See
                dashboard/INTEGRATION.md.
              </p>
              <button
                type="button"
                onClick={refetch}
                className="mt-3 rounded bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          ) : data ? (
            <div>
              {data.hazard_types?.length > 0 ? (
                <div className="mb-4 flex flex-wrap gap-2">
                  {data.hazard_types.map((hazard) => (
                    <HazardIcon key={hazard} hazard={hazard} />
                  ))}
                </div>
              ) : null}

              <dl className="mb-4 space-y-1 text-sm">
                {RAINFALL_ROWS.map(([field, label]) =>
                  data[field] != null ? (
                    <div key={field} className="flex justify-between">
                      <dt className="text-slate-500">{label}</dt>
                      <dd className="font-medium text-slate-800">
                        {data[field]} mm
                      </dd>
                    </div>
                  ) : null,
                )}
              </dl>

              <p className="rounded bg-slate-50 p-3 text-sm text-slate-600">
                {data.reason}
              </p>

              <button
                type="button"
                onClick={refetch}
                className="mt-4 rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
              >
                Refresh
              </button>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-slate-400">
              No data yet.
            </p>
          )}
        </div>
      </div>
    </PageContainer>
  )
}
