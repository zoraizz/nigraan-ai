import CategoryBadge from './CategoryBadge.jsx'
import { formatDay } from './timeFormat.js'

// Barrages whose modelled forecast reaches Low Flood or higher, soonest first.
// onRoute(row) opens What-if prefilled with that barrage's forecast peak.
export default function OutlookCard({ outlook, forecastDays, onRoute }) {
  const rows = Array.isArray(outlook) ? outlook : []
  return (
    <section className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5">
      <h2 className="text-sm font-semibold text-slate-100">Outlook</h2>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-[#c5d9cc]">
          No barrage is forecast to reach Low Flood in the next {forecastDays || 30} days.
        </p>
      ) : (
        <ul className="mt-1 space-y-2">
          {rows.map((row) => (
            <li key={row.name} className="border-t border-[#1b4a33]/70 pt-2 first:border-t-0 first:pt-0">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-slate-100">
                  {row.name} forecast {row.forecast_peak_category} on {formatDay(row.forecast_peak_date)}
                </p>
                <CategoryBadge category={row.forecast_peak_category} />
              </div>
              {row.first_crossing && (
                <p className="text-[11px] text-[#9dbdac]">
                  {row.first_crossing.category} or higher from {formatDay(row.first_crossing.date)}
                  {row.confidence === 'low confidence' ? ' · low confidence' : ''}
                </p>
              )}
              <button type="button" onClick={() => onRoute?.(row)}
                className="mt-1 rounded-md border border-emerald-500/40 px-2 py-1 text-[11px] font-semibold text-emerald-300 hover:bg-[#0c2918]">
                Route this forecast
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
