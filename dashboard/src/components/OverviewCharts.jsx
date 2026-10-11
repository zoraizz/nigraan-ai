import React from 'react'
import { DISTRICTS, HAZARD_LABELS } from '../config/districts.js'

// Key districts data for Saturation Comparison Chart
const COMPARISON_DISTRICTS = [
  { name: 'Dadu', memory90d: 284, forecast3d: 58 },
  { name: 'Rajanpur', memory90d: 260, forecast3d: 56 },
  { name: 'D.G. Khan', memory90d: 245, forecast3d: 52 },
  { name: 'Khairpur', memory90d: 195, forecast3d: 42 },
  { name: 'Chitral', memory90d: 190, forecast3d: 34 },
  { name: 'Jacobabad', memory90d: 180, forecast3d: 35 },
  { name: 'Tharparkar', memory90d: 38, forecast3d: 48 },
]

export function SaturationComparisonChart() {
  const maxVal = 350 // max mm height scale

  return (
    <div className="flex flex-col justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 shadow-lg h-full">
      {/* Title */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
            </svg>
          </div>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Illustrative comparison
          </span>
        </div>
        <span className="text-[11px] text-slate-400 font-mono">Illustrative scenario</span>
      </div>

      {/* SVG Bar Chart */}
      <div className="my-auto w-full pt-2">
        <div className="flex h-36 items-end justify-between gap-2 px-1 border-b border-[#1b4a33]">
          {COMPARISON_DISTRICTS.map((item) => {
            const memoryHeight = (item.memory90d / maxVal) * 100
            const forecastHeight = (item.forecast3d / maxVal) * 100

            return (
              <div key={item.name} className="flex flex-1 flex-col items-center gap-1 group">
                <div className="relative flex w-full items-end justify-center gap-1 h-full">
                  {/* 90-day memory bar */}
                  <div
                    className="w-2.5 rounded-t bg-gradient-to-t from-blue-700 to-cyan-400 transition-all duration-300 group-hover:brightness-125"
                    style={{ height: `${memoryHeight}%` }}
                    title={`${item.name} 90d: ${item.memory90d}mm`}
                  />
                  {/* 3-day forecast bar */}
                  <div
                    className="w-2.5 rounded-t bg-gradient-to-t from-rose-600 to-rose-400 transition-all duration-300 group-hover:brightness-125"
                    style={{ height: `${forecastHeight}%` }}
                    title={`${item.name} 3d: +${item.forecast3d}mm`}
                  />
                </div>
                <span className="text-[10px] font-medium text-slate-400 group-hover:text-slate-200 truncate max-w-[42px] text-center">
                  {item.name}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center justify-center gap-6 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-cyan-400" />
          Scenario 90-day (mm)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-rose-500" />
          Scenario 3-day (mm)
        </span>
      </div>
    </div>
  )
}

// Hazard Breakdown Donut Chart
export function HazardBreakdownChart() {
  const hazardCounts = [
    { key: 'flood', label: 'Flood', count: 9, color: '#3b82c4' },
    { key: 'glof', label: 'GLOF', count: 3, color: '#2e8f82' },
    { key: 'avalanche', label: 'Avalanche', count: 3, color: '#6fb8c9' },
    { key: 'landslide', label: 'Landslide', count: 2, color: '#b4532a' },
    { key: 'drought', label: 'Drought', count: 2, color: '#c08a2e' },
  ]

  const total = hazardCounts.reduce((acc, curr) => acc + curr.count, 0)

  // Calculate SVG strokeDasharray offsets for donut
  let cumulative = 0
  const circumference = 2 * Math.PI * 36 // radius = 36 -> circumference ≈ 226.19

  const slices = hazardCounts.map((item) => {
    const strokeDasharray = `${(item.count / total) * circumference} ${circumference}`
    const strokeDashoffset = -cumulative
    cumulative += (item.count / total) * circumference
    return { ...item, strokeDasharray, strokeDashoffset }
  })

  return (
    <div className="flex flex-col justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 shadow-lg h-full">
      {/* Title */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </div>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Hazard Breakdown
          </span>
        </div>
      </div>

      {/* Donut Chart & Compact Legend side by side */}
      <div className="my-auto flex items-center justify-around gap-2 py-1">
        {/* SVG Donut */}
        <div className="relative flex h-28 w-28 shrink-0 items-center justify-center">
          <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="36" fill="transparent" stroke="#1e293b" strokeWidth="12" />
            {slices.map((slice) => (
              <circle
                key={slice.key}
                cx="50"
                cy="50"
                r="36"
                fill="transparent"
                stroke={slice.color}
                strokeWidth="12"
                strokeDasharray={slice.strokeDasharray}
                strokeDashoffset={slice.strokeDashoffset}
                className="transition-all duration-500 hover:opacity-80"
              />
            ))}
          </svg>
          <div className="absolute flex flex-col items-center justify-center text-center">
            <span className="font-heading text-lg font-bold text-white">{DISTRICTS.length}</span>
            <span className="text-[9px] uppercase tracking-wider text-slate-400">Districts</span>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-1.5 text-xs">
          {hazardCounts.map((h) => (
            <div key={h.key} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-slate-300 text-[11px]">
                <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: h.color }} />
                {h.label}
              </span>
              <span className="font-mono text-[11px] font-bold text-slate-200">{h.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
