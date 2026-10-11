import { useState } from 'react'
import HeroCard from '../components/HeroCard.jsx'
import StatCard from '../components/StatCard.jsx'
import HydrologicalWidget from '../components/HydrologicalWidget.jsx'
import { SaturationComparisonChart, HazardBreakdownChart } from '../components/OverviewCharts.jsx'
import DistrictStatusGrid from '../components/DistrictStatusGrid.jsx'
import { DISTRICTS } from '../config/districts.js'

// Simple SVG Icons for Hero Cards
function AlertTriangleIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function HeartHandshakeIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0016.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 002 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
    </svg>
  )
}

function SatelliteScanIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  )
}

function GaugeIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M8 9l4 3 4-3" />
    </svg>
  )
}

export default function Overview() {
  // State for selected district (drives Hero Card 4 & Hydrological Widget)
  const [selectedDistrict, setSelectedDistrict] = useState(
    DISTRICTS.find((d) => d.name === 'Dadu') || DISTRICTS[0]
  )

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      {/* ── ROW 1: Title Bar & Command Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 px-4 py-3 shadow-lg">
        {/* Left Title & Subtitle */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#0a3a24] p-1 border border-emerald-500/30 shadow-md">
            <img src="/logo.png" alt="Nigraan AI Logo" className="h-full w-full object-contain" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-lg font-extrabold tracking-tight text-white">
                Nigraan <span className="text-[#3ddc84]">AI</span>
              </h1>
              <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400 border border-emerald-500/20">
                Command Center
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Illustrative scenario board. Live Open-Meteo assessments are on the Risk Map.
            </p>
          </div>
        </div>

        {/* Right Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* District Selector Chip */}
          <div className="flex items-center gap-1.5 rounded-lg border border-[#1b4a33]/80 bg-[#041208]/90 px-3 py-1.5 text-xs text-slate-300">
            <span className="text-slate-400 font-medium">Focused District:</span>
            <select
              value={selectedDistrict.name}
              onChange={(e) => {
                const found = DISTRICTS.find((d) => d.name === e.target.value)
                if (found) setSelectedDistrict(found)
              }}
              className="bg-transparent font-bold text-emerald-400 focus:outline-none cursor-pointer"
            >
              {DISTRICTS.map((d) => (
                <option key={d.name} value={d.name} className="bg-[#041208] text-slate-200">
                  {d.name} ({d.province})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 rounded-lg border border-[#1b4a33] bg-[#041208]/60 px-3 py-1.5 text-xs font-mono text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>Scenario board</span>
          </div>
        </div>
      </div>

      {/* ── ROW 2: Four Hero Cards (Equal Width) ── */}
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: Currently At Risk */}
        <HeroCard
          title="Flood scenario"
          value="Dadu District"
          subtitle="Illustrative example, not a live forecast"
          badgeText="DEMO"
          badgeColor="red"
          icon={AlertTriangleIcon}
          iconBg="bg-rose-500/15 text-rose-400 border-rose-500/30"
          actionLink="/risk-map"
          actionText="Open Risk Map"
        />

        {/* Card 2: Highest Need of Aid */}
        <HeroCard
          title="Aid scenario"
          value="Rajanpur"
          subtitle="Illustrative score, not a live ranking"
          badgeText="DEMO"
          badgeColor="orange"
          icon={HeartHandshakeIcon}
          iconBg="bg-amber-500/15 text-amber-400 border-amber-500/30"
          actionLink="/aid-priority"
          actionText="Open Aid Priority"
        />

        {/* Card 3: Assess Damage */}
        <HeroCard
          title="Assess Damage"
          value="Scene classifier"
          subtitle="Single image or tiled scene. Not a live scene count."
          badgeText="READY"
          badgeColor="emerald"
          icon={SatelliteScanIcon}
          iconBg="bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
          actionLink="/damage-assessment"
          actionText="Open Damage Assessment"
        />

        {/* Card 4: Saturation Index Summary */}
        <HeroCard
          title="Saturation Summary"
          value={`${selectedDistrict.name}`}
          subtitle="Illustrative scale, not a hydrological model"
          badgeText={selectedDistrict.name === 'Dadu' || selectedDistrict.name === 'Rajanpur' ? 'HIGH' : 'DEMO'}
          badgeColor={selectedDistrict.name === 'Dadu' || selectedDistrict.name === 'Rajanpur' ? 'red' : 'yellow'}
          icon={GaugeIcon}
          iconBg="bg-cyan-500/15 text-cyan-400 border-cyan-500/30"
        />
      </div>

      {/* ── ROW 3: Four Slim Stat Tiles (Centered) ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          value="16"
          label="Districts Monitored"
          subtext="Sindh, Punjab, KP, Balochistan, GB"
          accentColor="emerald"
        />
        <StatCard
          value="3"
          label="Scenario focus"
          subtext="Illustrative: Dadu, Rajanpur, D.G. Khan"
          accentColor="rose"
        />
        <StatCard
          value="38.4 mm"
          label="Scenario 3-day rain"
          subtext="Illustrative, not a live Open-Meteo average"
          accentColor="cyan"
        />
        <StatCard
          value="5"
          label="Active Hazard Types"
          subtext="Flood, GLOF, Avalanche, Landslide, Drought"
          accentColor="amber"
        />
      </div>

      {/* ── ROW 4: Three Side-by-Side Panels ── */}
      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-12">
        {/* Hydrological Widget (Narrow-to-medium: 4 cols) */}
        <div className="lg:col-span-4">
          <HydrologicalWidget district={selectedDistrict} />
        </div>

        {/* Saturation Comparison Chart (Widest: 5 cols) */}
        <div className="lg:col-span-5">
          <SaturationComparisonChart />
        </div>

        {/* Hazard Type Breakdown (Narrow: 3 cols) */}
        <div className="lg:col-span-3">
          <HazardBreakdownChart />
        </div>
      </div>

      {/* ── ROW 5: 16-District Matrix Panel (Full Width) ── */}
      <div>
        <DistrictStatusGrid
          selectedDistrict={selectedDistrict}
          onSelectDistrict={(dist) => setSelectedDistrict(dist)}
        />
      </div>
    </div>
  )
}
