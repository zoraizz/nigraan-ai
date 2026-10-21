import { floodCategory } from '../../config/floodCategories.js'
import CategoryBadge from './CategoryBadge.jsx'
import { formatDay, formatPeople } from './timeFormat.js'

const W = 72
const H = 20
const PAD = 2

// Forecast discharge as a tiny inline line. The y-axis runs from 0 to the
// larger of the forecast peak and the Low Flood threshold, so the dashed
// threshold line always shows how far the river is from Low Flood.
function Sparkline({ series, low, color, name }) {
  const values = (Array.isArray(series) ? series : []).map((row) => Number(row.cusecs)).filter(Number.isFinite)
  if (values.length < 2) return null
  const lowValue = Number(low)
  const hasLow = Number.isFinite(lowValue) && lowValue > 0
  const top = Math.max(...values, hasLow ? lowValue : 0) * 1.05 || 1
  const x = (i) => PAD + (i * (W - 2 * PAD)) / (values.length - 1)
  const y = (v) => H - PAD - (v / top) * (H - 2 * PAD)
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${name} forecast trend`} className="block">
      {hasLow && (
        <line x1={0} x2={W} y1={y(lowValue)} y2={y(lowValue)} stroke="#b6d94a" strokeWidth={1} strokeDasharray="2 2" opacity={0.7}>
          <title>Low Flood threshold {formatPeople(lowValue)} cusecs</title>
        </line>
      )}
      <polyline fill="none" stroke={color} strokeWidth={1.25} strokeLinejoin="round" points={points} />
    </svg>
  )
}

function compact(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n / 1000).toLocaleString('en-US')}k`
}

export default function ForecastTable({ rows, warnings }) {
  const list = Array.isArray(rows) ? rows : []
  const warningFor = (name) => (Array.isArray(warnings) ? warnings.find((w) => w.startsWith(`${name}:`)) : null)
  return (
    <section className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e]">
      <header className="border-b border-[#1b4a33]/70 px-2 py-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8aa898]">Barrage forecast</p>
        <p className="text-[11px] text-[#9dbdac]">Modelled cusecs (GloFAS, bias-scaled). Dashed line: Low Flood threshold.</p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs tabular-nums whitespace-nowrap">
          <thead className="bg-[#0a2416] text-[11px] uppercase tracking-wide text-[#8aa898]">
            <tr>
              <th className="px-2 py-1 font-semibold">Barrage</th>
              <th className="px-2 py-1 text-right font-semibold">Today</th>
              <th className="px-2 py-1 text-right font-semibold">Peak</th>
              <th className="px-2 py-1 font-semibold">Peak date</th>
              <th className="px-2 py-1 font-semibold">Category</th>
              <th className="px-2 py-1 font-semibold">Trend</th>
            </tr>
          </thead>
          <tbody>
            {list.map((row) => {
              const lowConfidence = row.confidence === 'low confidence' || row.calibrated === false
              return (
                <tr key={row.name} className="border-t border-[#1b4a33]/60">
                  <td className="px-2 py-1 font-medium text-slate-100">
                    {row.name}
                    {lowConfidence && (
                      <span title={warningFor(row.name) || 'Weak calibration against 2022 FFC gauges'}
                        className="ml-1.5 rounded bg-amber-500/15 px-1 py-0.5 text-[10px] font-semibold text-amber-300">
                        low confidence
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1 text-right text-slate-200" title={`${formatPeople(Math.round(row.today_cusecs))} cusecs`}>{compact(row.today_cusecs)}</td>
                  <td className="px-2 py-1 text-right text-slate-100" title={`${formatPeople(Math.round(row.forecast_peak_cusecs))} cusecs`}>{compact(row.forecast_peak_cusecs)}</td>
                  <td className="px-2 py-1 text-slate-300">{formatDay(row.forecast_peak_date)}</td>
                  <td className="px-2 py-1"><CategoryBadge category={row.forecast_peak_category} /></td>
                  <td className="px-2 py-1">
                    <Sparkline series={row.series} low={row.low_threshold_cusecs} name={row.name}
                      color={floodCategory(row.forecast_peak_category).color} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
