import React from 'react'

// Static scenario figures for the overview board. Live rainfall stays on
// Risk Flag (Open-Meteo cache, drought archive dates, 429 cooldown). This
// widget does not call Open-Meteo and is not a hydrological model.
const DISTRICT_HYDRO_SCENARIOS = {
  Dadu: { memory90d: 284, forecast3d: 58.5, insight: 'Scenario: high accumulation plus a large 3-day rain figure. Not a measured soil saturation.' },
  Khairpur: { memory90d: 195, forecast3d: 42.0, insight: 'Scenario: elevated accumulation along the Indus. Not a live river forecast.' },
  Sukkur: { memory90d: 165, forecast3d: 38.0, insight: 'Scenario: moderate accumulation near the barrage sector. Not a live discharge reading.' },
  Larkana: { memory90d: 210, forecast3d: 45.2, insight: 'Scenario: high accumulation in the right-bank canals. Not a measured drainage capacity.' },
  Jacobabad: { memory90d: 180, forecast3d: 35.0, insight: 'Scenario: moderate accumulation. Not a live canal gauge.' },
  Jaffarabad: { memory90d: 230, forecast3d: 48.0, insight: 'Scenario: high accumulation on flat ground. Not a measured standing-water duration.' },
  'D.I. Khan': { memory90d: 140, forecast3d: 28.5, insight: 'Scenario: moderate hill-torrent accumulation. Not a live Rod-Kohi gauge.' },
  'D.G. Khan': { memory90d: 245, forecast3d: 52.0, insight: 'Scenario: high hill-torrent accumulation. Not a measured runoff volume.' },
  Rajanpur: { memory90d: 260, forecast3d: 56.4, insight: 'Scenario: high accumulation in a priority flood sector. Not a live defense status.' },
  Chitral: { memory90d: 190, forecast3d: 34.0, insight: 'Scenario only. GLOF and avalanche risk are not computed from this bar.' },
  Hunza: { memory90d: 135, forecast3d: 22.0, insight: 'Scenario only. Glacial-lake state is not measured here.' },
  Skardu: { memory90d: 120, forecast3d: 18.5, insight: 'Scenario only. Snowpack stability is not measured here.' },
  Mansehra: { memory90d: 205, forecast3d: 41.0, insight: 'Scenario: steep-terrain accumulation. Not a measured landslide probability.' },
  Battagram: { memory90d: 175, forecast3d: 36.5, insight: 'Scenario: moderate slope accumulation. Not a measured slip probability.' },
  Chagai: { memory90d: 22, forecast3d: 1.2, insight: 'Scenario: very low accumulation in an arid district. Not a live drought index.' },
  Tharparkar: { memory90d: 38, forecast3d: 48.0, insight: 'Scenario: low stored rain plus a larger forecast figure. Not a live drought index.' },
}

export default function HydrologicalWidget({ district }) {
  const districtName = district?.name || 'Dadu'
  const data = DISTRICT_HYDRO_SCENARIOS[districtName] || DISTRICT_HYDRO_SCENARIOS.Dadu

  // Display scale only. 300 mm is not a soil-capacity measurement.
  const totalAccumulation = data.memory90d + data.forecast3d
  const saturationPercent = Math.min(100, Math.round((totalAccumulation / 300) * 100))

  let riskCategory = { label: 'SCENARIO', color: 'emerald', bg: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' }
  if (saturationPercent >= 85) {
    riskCategory = { label: 'SCENARIO HIGH', color: 'rose', bg: 'bg-rose-500/15 text-rose-400 border-rose-500/30' }
  } else if (saturationPercent >= 65) {
    riskCategory = { label: 'SCENARIO ELEVATED', color: 'amber', bg: 'bg-amber-500/15 text-amber-400 border-amber-500/30' }
  } else if (saturationPercent >= 40) {
    riskCategory = { label: 'SCENARIO MODERATE', color: 'yellow', bg: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30' }
  }

  const baselineWidth = Math.min(100, Math.round((data.memory90d / 300) * 100))
  const forecastWidth = Math.min(100 - baselineWidth, Math.round((data.forecast3d / 300) * 100))

  return (
    <div className="flex flex-col justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 shadow-lg h-full">
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
              </svg>
            </div>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Illustrative saturation
            </span>
          </div>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-bold tracking-wider ${riskCategory.bg}`}>
            {riskCategory.label}
          </span>
        </div>

        <p className="mt-2 text-[11px] leading-snug text-slate-400">
          Scenario bars for the selected district. Not live Open-Meteo, and not a hydrological model.
        </p>

        <div className="mt-2 flex items-baseline justify-between">
          <span className="text-sm font-bold text-white">{districtName} District</span>
          <span className="text-xs font-mono font-bold text-cyan-400">
            Scale {saturationPercent}%
          </span>
        </div>

        <div className="mt-3">
          <div className="relative h-3 w-full rounded-full bg-[#041208] border border-[#1b4a33] overflow-hidden flex">
            <div
              className="h-full bg-gradient-to-r from-blue-600 to-cyan-500 transition-all duration-500"
              style={{ width: `${baselineWidth}%` }}
              title={`Scenario 90-day figure: ${data.memory90d} mm`}
            />
            <div
              className="h-full bg-rose-500 transition-all duration-500"
              style={{ width: `${Math.max(3, forecastWidth)}%` }}
              title={`Scenario 3-day figure: ${data.forecast3d} mm`}
            />
          </div>

          <div className="mt-2 flex justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-cyan-400" />
              90d figure: <strong className="text-slate-200">{data.memory90d} mm</strong>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-400" />
              3d figure: <strong className="text-slate-200">+{data.forecast3d} mm</strong>
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-[#1b4a33] bg-[#061008] p-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-cyan-400 mb-1">
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>Scenario note</span>
        </div>
        <p className="text-[11px] text-slate-300 leading-snug">
          {data.insight}
        </p>
      </div>
    </div>
  )
}
