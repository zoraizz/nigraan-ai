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
  const rows = Array.isArray(etas) ? etas : []
  return (
    <section className="shrink-0 overflow-hidden rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] lg:max-h-[46%] lg:overflow-auto">
      <header className="px-3 py-2">
        <h2 className="text-sm font-semibold text-slate-100">Downstream peaks</h2>
        <p className="text-[11px] text-[#9dbdac]">Estimates with a range. Arrived rows use the observed time.</p>
      </header>
      {rows.length === 0 ? (
        <p className="border-t border-[#1b4a33]/70 px-3 py-3 text-sm text-[#9dbdac]">No downstream peak in this step.</p>
      ) : (
        <ul>
          {rows.map((eta) => (
            <EtaRow key={`${eta.wave_id || 'wave'}-${eta.barrage}`} eta={eta} />
          ))}
        </ul>
      )}
    </section>
  )
}
