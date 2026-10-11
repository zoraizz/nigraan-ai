import React, { useState, useMemo } from 'react'
import { DISTRICTS, HAZARD_LABELS } from '../config/districts.js'

// Multi-hazard pill color lookup
const HAZARD_PILL_COLORS = {
  flood: 'bg-[#3b82c4]/20 text-[#60a5fa] border-[#3b82c4]/40',
  glof: 'bg-[#2e8f82]/20 text-[#2dd4bf] border-[#2e8f82]/40',
  avalanche: 'bg-[#6fb8c9]/20 text-[#38bdf8] border-[#6fb8c9]/40',
  landslide: 'bg-[#b4532a]/20 text-[#fb923c] border-[#b4532a]/40',
  drought: 'bg-[#c08a2e]/20 text-[#facc15] border-[#c08a2e]/40',
}

// Assigned Status ring + score mapping for the 16 districts
const DISTRICT_STATUS_MAP = {
  Dadu: { status: 'URGENT', ring: 'border-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.4)]', score: 92 },
  Rajanpur: { status: 'URGENT', ring: 'border-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.4)]', score: 89 },
  'D.G. Khan': { status: 'URGENT', ring: 'border-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.4)]', score: 85 },
  Khairpur: { status: 'HIGH', ring: 'border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.4)]', score: 78 },
  Chitral: { status: 'HIGH', ring: 'border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.4)]', score: 74 },
  Jacobabad: { status: 'HIGH', ring: 'border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.4)]', score: 71 },
  Larkana: { status: 'HIGH', ring: 'border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.4)]', score: 69 },
  Mansehra: { status: 'MEDIUM', ring: 'border-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.4)]', score: 58 },
  Sukkur: { status: 'MEDIUM', ring: 'border-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.4)]', score: 55 },
  Jaffarabad: { status: 'MEDIUM', ring: 'border-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.4)]', score: 54 },
  'D.I. Khan': { status: 'MEDIUM', ring: 'border-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.4)]', score: 52 },
  Battagram: { status: 'MONITOR', ring: 'border-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.4)]', score: 38 },
  Hunza: { status: 'MONITOR', ring: 'border-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.4)]', score: 35 },
  Skardu: { status: 'MONITOR', ring: 'border-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.4)]', score: 32 },
  Tharparkar: { status: 'MONITOR', ring: 'border-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.4)]', score: 28 },
  Chagai: { status: 'MONITOR', ring: 'border-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.4)]', score: 22 },
}

export default function DistrictStatusGrid({ selectedDistrict, onSelectDistrict }) {
  const [provinceFilter, setProvinceFilter] = useState('ALL')
  const [hazardFilter, setHazardFilter] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')

  const provinces = ['ALL', 'Sindh', 'Punjab', 'Khyber Pakhtunkhwa', 'Balochistan', 'Gilgit-Baltistan']
  const hazards = ['ALL', 'flood', 'glof', 'avalanche', 'landslide', 'drought']

  const filteredDistricts = useMemo(() => {
    return DISTRICTS.filter((d) => {
      const matchProv = provinceFilter === 'ALL' || d.province === provinceFilter
      const matchHaz = hazardFilter === 'ALL' || d.hazards.includes(hazardFilter)
      const matchSearch =
        d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.province.toLowerCase().includes(searchQuery.toLowerCase())

      return matchProv && matchHaz && matchSearch
    })
  }, [provinceFilter, hazardFilter, searchQuery])

  return (
    <div className="rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 shadow-lg">
      {/* Panel Header & One-Line Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[#1b4a33]">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-bold tracking-tight text-white">
              16-District Monitored Matrix
            </h2>
            <p className="text-[11px] text-slate-400">
              Illustrative status rings, not live Risk Flag scores
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search district..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 rounded-lg border border-[#1b4a33]/70 bg-[#041208]/80 px-2.5 pl-8 text-xs text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
            />
            <svg
              className="absolute left-2.5 top-2 h-3.5 w-3.5 text-[#6f8f7e]"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
                clipRule="evenodd"
              />
            </svg>
          </div>

          {/* Province Dropdown */}
          <select
            value={provinceFilter}
            onChange={(e) => setProvinceFilter(e.target.value)}
            className="h-8 rounded-lg border border-[#1b4a33]/70 bg-[#041208]/80 px-2.5 text-xs text-slate-200 focus:border-emerald-500 focus:outline-none"
          >
            {provinces.map((prov) => (
              <option key={prov} value={prov} className="bg-[#041208] text-slate-200">
                {prov === 'ALL' ? 'All Provinces' : prov}
              </option>
            ))}
          </select>

          {/* Hazard Filter Chips */}
          <div className="flex items-center gap-1 bg-[#041208]/80 p-0.5 rounded-lg border border-[#1b4a33]/70">
            {hazards.map((haz) => (
              <button
                key={haz}
                onClick={() => setHazardFilter(haz)}
                type="button"
                className={`px-2 py-1 text-[10px] font-semibold rounded-md transition-colors ${
                  hazardFilter === haz
                    ? 'bg-emerald-500 text-slate-950 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {haz === 'ALL' ? 'All' : HAZARD_LABELS[haz] || haz}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Grid Container with internal scrolling */}
      <div className="mt-3 max-h-[360px] overflow-y-auto pr-1">
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {filteredDistricts.map((district) => {
            const statusInfo = DISTRICT_STATUS_MAP[district.name] || {
              status: 'MONITOR',
              ring: 'border-emerald-400',
              score: 30,
            }
            const isSelected = selectedDistrict?.name === district.name

            return (
              <div
                key={district.name}
                onClick={() => onSelectDistrict && onSelectDistrict(district)}
                className={`group cursor-pointer rounded-lg border p-3 transition-all ${
                  isSelected
                    ? 'border-emerald-500 bg-emerald-500/10 shadow-[0_0_12px_rgba(16,185,129,0.2)]'
                    : 'border-[#1b4a33] bg-[#061410] hover:border-slate-700 hover:bg-[#0a2010]'
                }`}
              >
                <div className="flex items-center gap-3">
                  {/* Status Ring Avatar */}
                  <div
                    className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 bg-[#041208] font-heading font-extrabold text-xs text-white ${statusInfo.ring}`}
                  >
                    {district.name.substring(0, 2).toUpperCase()}
                  </div>

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h3 className="truncate font-heading text-xs font-bold text-white group-hover:text-emerald-400 transition-colors">
                        {district.name}
                      </h3>
                      <span className="text-[10px] font-mono text-slate-400">
                        {statusInfo.score}%
                      </span>
                    </div>

                    <p className="truncate text-[10px] text-slate-400">{district.province}</p>

                    {/* Multi-hazard mini pills */}
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {district.hazards.map((h) => (
                        <span
                          key={h}
                          className={`inline-flex items-center rounded border px-1.5 py-0.2 text-[9px] font-medium uppercase tracking-wider ${
                            HAZARD_PILL_COLORS[h] || 'bg-[#0a2418] text-slate-300'
                          }`}
                        >
                          {HAZARD_LABELS[h] || h}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {filteredDistricts.length === 0 && (
          <div className="py-8 text-center text-xs text-slate-400">
            No districts match the selected filters.
          </div>
        )}
      </div>
    </div>
  )
}
