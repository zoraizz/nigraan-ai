import React, { useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import HazardIcon from '../components/HazardIcon.jsx'
import RiskDetailModal from '../components/RiskDetailModal.jsx'
import { DISTRICTS } from '../config/districts.js'
import { DISTRICT_DETAILS } from '../config/districtDetails.js'

function GridIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}

function ListIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

export default function RiskMap() {
  const [activeModalDistrict, setActiveModalDistrict] = useState(null)
  const [viewMode, setViewMode] = useState('list') // Defaults to List view as requested

  return (
    <PageContainer
      title="District Risk Map"
      lead="Click a district to open its live Risk Flag assessment. Card temperatures, rain, snow, and river figures are static scenario context. Live Open-Meteo metrics, including snowfall, and the availability banner are inside the assessment."
    >
      {/* Top Controls: View Switcher (List vs Grid) */}
      <div className="mb-4 flex items-center justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 px-4 py-2.5 shadow-md">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <span>Layout View:</span>
          <span className="text-emerald-400 uppercase font-mono tracking-wider font-bold">
            {viewMode} Mode
          </span>
        </div>

        {/* View Mode Switcher Toggle */}
        <div className="flex items-center gap-1 rounded-lg border border-[#1b4a33]/70 bg-[#041208]/90 p-1">
          <button
            onClick={() => setViewMode('list')}
            type="button"
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
              viewMode === 'list'
                ? 'bg-emerald-500 text-slate-950 font-bold shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <ListIcon />
            <span>List View</span>
          </button>
          <button
            onClick={() => setViewMode('grid')}
            type="button"
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
              viewMode === 'grid'
                ? 'bg-emerald-500 text-slate-950 font-bold shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <GridIcon />
            <span>Grid Boxes</span>
          </button>
        </div>
      </div>

      {/* ── LIST VIEW MODE ── */}
      {viewMode === 'list' ? (
        <div className="space-y-3">
          {DISTRICTS.map((entry) => {
            const details = DISTRICT_DETAILS[entry.name] || {
              history: 'Historical hazard monitoring active.',
              temp: '30°C',
              humidity: '50%',
              attributeLabel: 'Risk Score',
              attributeValue: 'Monitored',
              attributeSubtext: 'Standard Feed',
            }

            return (
              <div
                key={entry.name}
                onClick={() => setActiveModalDistrict(entry.name)}
                className="group flex flex-wrap md:flex-nowrap items-center justify-between gap-4 rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 transition-all duration-200 hover:border-emerald-500/60 hover:bg-[#0e3020] hover:shadow-lg cursor-pointer"
              >
                {/* Column 1: Name, Province & Hazard Pills */}
                <div className="w-full md:w-1/4 shrink-0">
                  <div className="flex items-center justify-between md:justify-start gap-2">
                    <h3 className="font-heading text-base font-bold text-white group-hover:text-emerald-400 transition-colors">
                      {entry.name}
                    </h3>
                    <div className="flex items-center gap-1">
                      {entry.hazards.map((hazard) => (
                        <HazardIcon key={hazard} hazard={hazard} />
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">{entry.province}</p>
                </div>

                {/* Column 2: Disaster History */}
                <div className="w-full md:w-2/5 flex-1 border-t md:border-t-0 md:border-l border-[#1b4a33]/80 pt-2 md:pt-0 md:pl-4">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                    Disaster History
                  </span>
                  <p className="text-xs text-slate-300 leading-snug line-clamp-2 mt-0.5">
                    {details.history}
                  </p>
                </div>

                {/* Column 3: Weather & Hazard Attribute */}
                <div className="w-full md:w-auto shrink-0 flex items-center gap-3 border-t md:border-t-0 md:border-l border-[#1b4a33]/80 pt-2 md:pt-0 md:pl-4">
                  <div className="flex flex-col text-xs text-slate-300 gap-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Scenario</span>
                    <span className="flex items-center gap-1 font-mono">
                      <span className="text-amber-400">🌡</span> {details.temp}
                    </span>
                    <span className="flex items-center gap-1 font-mono">
                      <span className="text-cyan-400">💧</span> {details.humidity}
                    </span>
                  </div>

                  <div className="rounded-lg border border-[#1b4a33] bg-[#071208] px-3 py-1.5 min-w-[140px]">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                      {details.attributeLabel}
                    </span>
                    <span className="font-mono text-xs font-bold text-emerald-400 block">
                      {details.attributeValue}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400 block">
                      {details.attributeSubtext}
                    </span>
                  </div>
                </div>

                {/* Column 4: View Assessment Button */}
                <div className="w-full md:w-auto shrink-0 flex justify-end">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2 text-xs font-bold text-emerald-400 group-hover:bg-emerald-500 group-hover:text-slate-950 transition-all"
                  >
                    <span>View Assessment</span>
                    <svg className="h-3.5 w-3.5 transform group-hover:translate-x-1 transition-transform" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.16 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                    </svg>
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* ── GRID BOXES VIEW MODE ── */
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {DISTRICTS.map((entry) => {
            const details = DISTRICT_DETAILS[entry.name] || {
              history: 'Historical hazard monitoring active.',
              temp: '30°C',
              humidity: '50%',
              attributeLabel: 'Risk Score',
              attributeValue: 'Monitored',
              attributeSubtext: 'Standard Feed',
            }

            return (
              <div
                key={entry.name}
                onClick={() => setActiveModalDistrict(entry.name)}
                className="group relative flex flex-col justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 transition-all duration-200 hover:border-emerald-500/60 hover:bg-[#0e3020] hover:shadow-xl cursor-pointer"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 border-b border-[#1b4a33]/80 pb-3 mb-3">
                    <div>
                      <h3 className="font-heading text-base font-bold text-white group-hover:text-emerald-400 transition-colors">
                        {entry.name}
                      </h3>
                      <p className="text-xs text-slate-400">{entry.province}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      {entry.hazards.map((hazard) => (
                        <HazardIcon key={hazard} hazard={hazard} />
                      ))}
                    </div>
                  </div>

                  <div className="mb-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Disaster History
                    </span>
                    <p className="mt-1 text-xs text-slate-300 leading-snug line-clamp-3">
                      {details.history}
                    </p>
                  </div>
                </div>

                <div className="mt-2 pt-3 border-t border-[#1b4a33]/60">
                  <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">Scenario</p>
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="flex items-center gap-1 text-slate-300 font-mono">
                      <span className="text-amber-400">🌡</span> {details.temp}
                    </span>
                    <span className="flex items-center gap-1 text-slate-300 font-mono">
                      <span className="text-cyan-400">💧</span> {details.humidity}
                    </span>
                  </div>

                  <div className="rounded-lg border border-[#1b4a33] bg-[#071208] p-2 flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                        {details.attributeLabel}
                      </span>
                      <span className="font-mono text-xs font-bold text-emerald-400">
                        {details.attributeValue}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">
                      {details.attributeSubtext}
                    </span>
                  </div>

                  <div className="mt-3 flex items-center justify-between text-[11px] text-emerald-400 font-semibold group-hover:text-emerald-300">
                    <span>Click for Full Assessment</span>
                    <svg className="h-3.5 w-3.5 transform group-hover:translate-x-1 transition-transform" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.16 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                    </svg>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Popup Overlay Modal */}
      {activeModalDistrict && (
        <RiskDetailModal
          districtName={activeModalDistrict}
          onClose={() => setActiveModalDistrict(null)}
        />
      )}
    </PageContainer>
  )
}
