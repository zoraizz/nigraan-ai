import { useState } from 'react'
import { waveName } from '../../api/floodTracker.js'
import { formatPeakLine, formatWall } from './timeFormat.js'

function hoursLabel(hours) {
  const value = Number(hours)
  if (!Number.isFinite(value)) return null
  if (value < 0) return `${Math.abs(value)} h before this step`
  if (value === 0) return 'at this step'
  return `${value} h from this step`
}

function EtaRow({ eta }) {
  const arrived = eta.status === 'arrived'
  const relative = hoursLabel(eta.hours_from_now)
  return (
    <li className="border-t border-[#1b4a33]/70 px-3 py-2.5 first:border-t-0">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-snug text-slate-100">{formatPeakLine(eta)}</p>
        <span className="shrink-0 rounded bg-[#0e3a28] px-1.5 py-0.5 text-[10px] font-semibold text-[#c5d9cc]">
          {waveName(eta)}
        </span>
      </div>
      <p className="mt-1 text-[11px] text-[#9dbdac]">
        {arrived ? 'Observed peak' : 'Estimate'}
        {eta.from_barrage ? ` · from ${eta.from_barrage}` : ''}
        {relative ? ` · ${relative}` : ''}
      </p>
      {!arrived && eta.eta_low && eta.eta_high && (
        <p className="mt-0.5 font-mono text-[10px] text-[#7f9c8c]">
          Window {formatWall(eta.eta_low)} – {formatWall(eta.eta_high)}
        </p>
      )}
    </li>
  )
}

export default function EtaPanel({ etas }) {
  const [showAll, setShowAll] = useState(false)
  const rows = (Array.isArray(etas) ? etas : []).slice().sort((a, b) => {
    const aArrived = a.status === 'arrived'
    const bArrived = b.status === 'arrived'
    if (aArrived !== bArrived) return aArrived ? 1 : -1
    const left = aArrived ? (a.observed_time || a.eta || '') : (a.eta || '9999')
    const right = bArrived ? (b.observed_time || b.eta || '') : (b.eta || '9999')
    return aArrived ? right.localeCompare(left) : left.localeCompare(right)
  })
  const visibleRows = showAll ? rows : rows.slice(0, 4)
  return (
    <section className="shrink-0 overflow-hidden rounded-xl border border-[#1b4a33]/80 bg-[#071a0e]">
      <header className="px-3 py-2">
        <h2 className="text-sm font-semibold text-slate-100">Downstream peaks</h2>
        <p className="text-[11px] text-[#9dbdac]">Estimates with a range. Arrived rows use the observed time.</p>
      </header>
      {rows.length === 0 ? (
        <p className="border-t border-[#1b4a33]/70 px-3 py-3 text-sm text-[#9dbdac]">No downstream peak in this step.</p>
      ) : (
        <ul>
          {visibleRows.map((eta) => (
            <EtaRow key={`${eta.wave_id || 'wave'}-${eta.barrage}`} eta={eta} />
          ))}
        </ul>
      )}
      {rows.length > 4 && (
        <button type="button" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}
          className="w-full border-t border-[#1b4a33]/70 px-3 py-2 text-left text-xs font-semibold text-emerald-300 hover:bg-[#0c2918]">
          {showAll ? 'Show less' : 'Show all'}
        </button>
      )}
    </section>
  )
}
