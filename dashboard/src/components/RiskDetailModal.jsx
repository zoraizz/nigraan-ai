import React, { useState, useEffect } from 'react'
import RiskBadge from './RiskBadge.jsx'
import HazardIcon from './HazardIcon.jsx'
import { useRiskData } from '../hooks/useRiskData.js'
import { DISTRICTS } from '../config/districts.js'
import { DISTRICT_DETAILS } from '../config/districtDetails.js'
import { buildRiskMetricRows, formatMetricValue } from '../pages/riskMetrics.js'
import { availabilityBanner } from '../pages/availabilityNote.js'

function reasoningLabel(source) {
  if (source === 'gemini') return 'Gemini'
  if (source === 'grok') return 'Grok'
  if (source === 'fallback') return 'Rule fallback'
  if (source === 'cache') return 'Cached response'
  return null
}

const LOADING_MESSAGES = [
  'Fetching the weather forecast…',
  'Reading the district’s hazard context…',
  'Asking the risk model for a level…',
  'Still working. The model can take a while…',
]

function WeatherMetrics({ data }) {
  const rows = buildRiskMetricRows(data)
  const showDischargeNote = rows.some((row) => row.discharge)
  const showSnowNote = rows.some((row) => row.snow)

  if (rows.length === 0) {
    return (
      <p className="mb-3 text-xs text-slate-400">No live weather metrics available for this district.</p>
    )
  }

  return (
    <div className="mb-4 rounded-xl border border-[#1b4a33]/80 bg-[#041208]/60 p-3.5">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
        Live Weather Metrics (Open-Meteo)
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {rows.map((row) => (
          <div
            key={row.key}
            className="flex items-baseline justify-between gap-2 border-b border-[#1b4a33]/60 pb-1"
          >
            <dt className={row.relevant ? 'text-slate-200 font-medium' : 'text-slate-400'}>{row.label}</dt>
            <dd className={`font-mono ${row.relevant ? 'font-bold text-emerald-400' : 'text-slate-400'}`}>
              {formatMetricValue(row.value, row.digits)} {row.unit}
            </dd>
          </div>
        ))}
      </dl>
      {showDischargeNote ? (
        <p className="mt-2 text-[10px] text-slate-400">
          River discharge cell derived from GloFAS model grid (~5 km resolution).
        </p>
      ) : showSnowNote ? (
        <p className="mt-2 text-[10px] text-slate-400">
          Snowfall represents 3-day sum; snow depth is latest forecast hour.
        </p>
      ) : null}
    </div>
  )
}

export default function RiskDetailModal({ districtName, onClose }) {
  const { data, loading, error, refetch, elapsed } = useRiskData(districtName)
  const [msgIdx, setMsgIdx] = useState(0)

  const districtObj = DISTRICTS.find((d) => d.name === districtName) || DISTRICTS[0]
  const details = DISTRICT_DETAILS[districtName] || DISTRICT_DETAILS.Dadu
  const coords = districtObj?.coords
  const banner = availabilityBanner(data)
  const sourceLabel = reasoningLabel(data?.reasoning_source)

  // Rotate loading message
  useEffect(() => {
    if (!loading) {
      setMsgIdx(0)
      return
    }
    const id = setInterval(
      () => setMsgIdx((i) => (i + 1) % LOADING_MESSAGES.length),
      25000
    )
    return () => clearInterval(id)
  }, [loading, districtName])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 animate-fadeIn"
      onClick={onClose}
    >
      {/* Modal Dialog Window */}
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-[#1b4a33] bg-[#071a0e] p-6 shadow-2xl text-slate-100 transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          type="button"
          aria-label="Close modal"
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-lg border border-[#1b4a33]/60 bg-[#0a2418]/40 text-slate-400 hover:bg-[#0e3a28] hover:text-white transition-colors"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 pr-10 border-b border-[#1b4a33] pb-4 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-heading text-xl font-bold text-white tracking-tight">
                {districtName} District
              </h2>
              <span className="text-xs font-semibold text-slate-400">
                ({districtObj.province})
              </span>
            </div>
            {coords && (
              <p className="mt-1 font-mono text-xs text-slate-400">
                Coordinates: {coords[0].toFixed(4)}° N, {coords[1].toFixed(4)}° E
              </p>
            )}
          </div>
          {data ? <RiskBadge level={data.risk_level} /> : null}
        </div>

        {/* Hazard Pills */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Hazards Monitored:
          </span>
          {districtObj.hazards.map((h) => (
            <HazardIcon key={h} hazard={h} />
          ))}
        </div>

        {/* Historical Context Callout */}
        <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-slate-300">
          <span className="font-bold text-emerald-400">Disaster Context: </span>
          {details.history}
        </div>

        {/* Modal Body: Loading State */}
        {loading ? (
          <div className="py-12 text-center">
            <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
            <p className="text-sm font-semibold text-white">{LOADING_MESSAGES[msgIdx]}</p>
            <p className="mt-2 font-mono text-xs text-slate-400">
              Elapsed: {elapsed}s{elapsed >= 8 ? ' · Service waking up, can take up to 60 seconds' : ''}
            </p>
          </div>
        ) : error ? (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-300">
            <p className="font-bold text-sm text-rose-400">Could not load the risk assessment</p>
            <p className="mt-1">{error.message}</p>
            <p className="mt-2 text-[11px] text-slate-400">
              The service may be waking up, which can take up to 60 seconds. Try again.
            </p>
            <button
              type="button"
              onClick={refetch}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-rose-500 px-3 py-1.5 font-bold text-slate-950 hover:bg-rose-400 transition-colors"
            >
              Retry Connection
            </button>
          </div>
        ) : data ? (
          <div>
            {/* Cache / Partial banners */}
            {data.cached && (
              <div className="mb-3 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-3 py-1.5 text-xs text-emerald-300">
                Returned from server cache (pre-warmed, no new model call)
              </div>
            )}
            {banner && (
              <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/15 px-3 py-1.5 text-xs text-amber-300">
                ⚠ {banner}
              </div>
            )}

            {/* Live Weather Metrics */}
            <WeatherMetrics data={data} />

            {/* Gemini AI Rationale / Explanation */}
            <div className="mb-4">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Risk synthesis{sourceLabel ? ` · ${sourceLabel}` : ''}
              </p>
              <div className="rounded-xl border border-[#1b4a33] bg-[#050f07] p-4 text-xs text-slate-200 leading-relaxed font-sans shadow-inner">
                {data.reason || 'No detailed analysis reasoning returned.'}
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="flex items-center justify-between border-t border-[#1b4a33] pt-4 mt-4">
              <span className="text-[11px] font-mono text-slate-400">
                Risk Flag API Model Response
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={refetch}
                  className="rounded-lg border border-slate-700 bg-[#0a2418] px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-[#0e3a28] hover:text-white transition-colors"
                >
                  Refresh Live Data
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg bg-emerald-500 px-4 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
