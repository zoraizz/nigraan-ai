import { useState } from 'react'
import { formatPeople, formatWall, uncertaintyHours } from './timeFormat.js'

function byEta(a, b) {
  const left = a?.eta || '9999'
  const right = b?.eta || '9999'
  if (left !== right) return left < right ? -1 : 1
  return (Number(a?.hours_to_arrival) || 0) - (Number(b?.hours_to_arrival) || 0)
}

function etaCell(village) {
  const when = formatWall(village.eta)
  const band = uncertaintyHours(village.eta_low, village.eta, village.eta_high)
  const hours = Number(village.hours_to_arrival)
  let relative = ''
  if (Number.isFinite(hours)) {
    relative = hours < 0 ? `${Math.abs(hours)} h ago` : `in ${hours} h`
  }
  const estimate = village.eta ? when : '—'
  const bandText = band == null ? '' : ` ±${band}h`
  return { estimate, bandText, relative }
}

// showDistance: extra Distance column (river_distance_km), What-if and Today only.
export default function AtRiskTable({ villages, selectedId, onSelect, showDistance = false }) {
  const [showAll, setShowAll] = useState(false)
  const rows = (Array.isArray(villages) ? villages : []).slice().sort(byEta)
  const visibleRows = showAll ? rows : rows.slice(0, 15)
  const total = rows.reduce((sum, village) => sum + (Number(village.population) || 0), 0)

  return (
    <section className="flex min-h-[240px] flex-col rounded-xl border border-[#1b4a33]/80 bg-[#071a0e]">
      <header className="shrink-0 border-b border-[#1b4a33]/70 px-2 py-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8aa898]">At risk this step</p>
        <p className="font-mono text-base text-slate-100">
          Est. {formatPeople(total)} <span className="text-xs font-sans text-[#9dbdac]">people</span>
        </p>
        <p className="text-[11px] text-[#9dbdac]">Estimated population, sorted by ETA. Not a census extract. A row opens the alert draft and rings the village.</p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs tabular-nums whitespace-nowrap">
          <thead className="sticky top-0 bg-[#0a2416] text-[11px] uppercase tracking-wide text-[#8aa898]">
            <tr>
              <th className="px-2 py-1 font-semibold">Village</th>
              <th className="px-2 py-1 font-semibold">District</th>
              <th className="px-2 py-1 font-semibold">ETA</th>
              {showDistance && <th className="px-2 py-1 text-right font-semibold">Distance</th>}
              <th className="px-2 py-1 text-right font-semibold">Est. population</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={showDistance ? 5 : 4} className="px-3 py-4 text-[#9dbdac]">No villages in this step.</td>
              </tr>
            ) : visibleRows.map((village) => {
              const selected = village.id === selectedId
              const cell = etaCell(village)
              return (
                <tr
                  key={village.id}
                  tabIndex={0}
                  aria-selected={selected}
                  aria-label={`Open alert draft for ${village.name}, ${village.district}`}
                  onClick={() => onSelect?.(village.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onSelect?.(village.id)
                    }
                  }}
                  className={`cursor-pointer border-t border-[#1b4a33]/60 outline-none focus-visible:bg-emerald-500/15 ${
                    selected ? 'bg-emerald-500/10' : 'hover:bg-[#0c2918]'
                  }`}
                >
                  <td className="px-2 py-1 font-medium text-slate-100" title={village.name}><span className="block max-w-24 truncate">{village.name}</span></td>
                  <td className="px-2 py-1 text-slate-300" title={village.district}><span className="block max-w-20 truncate">{village.district}</span></td>
                  <td className="px-2 py-1 text-slate-100" title={`Estimated arrival: ${cell.estimate}${cell.bandText} · ${cell.relative}`}>
                    {cell.estimate}{cell.bandText}
                  </td>
                  {showDistance && (
                    <td className="px-2 py-1 text-right text-slate-300" title="Distance to the river centreline">
                      {village.river_distance_km == null ? '—' : `${Number(village.river_distance_km).toFixed(1)} km`}
                    </td>
                  )}
                  <td
                    className="px-2 py-1 text-right text-slate-200"
                    title={village.population_source || 'Estimated population'}
                  >
                    {formatPeople(village.population)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {rows.length > 15 && (
        <button type="button" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}
          className="border-t border-[#1b4a33]/70 px-2 py-1 text-left text-xs font-semibold text-emerald-300 hover:bg-[#0c2918]">
          {showAll ? 'Show first 15' : `Show all ${rows.length}`}
        </button>
      )}
    </section>
  )
}
