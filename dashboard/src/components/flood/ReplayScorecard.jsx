import { waveName } from '../../api/floodTracker.js'
import { formatSignedHours, formatWall } from './timeFormat.js'

export default function ReplayScorecard({ rows, note, usingFixtures }) {
  const list = Array.isArray(rows) ? rows : []
  const within24 = list.filter((row) => row.error_hours != null && Number.isFinite(Number(row.error_hours)) && Math.abs(Number(row.error_hours)) <= 24).length
  const footnotes = [...new Set(list.map((row) => row.note).filter(Boolean))]
  return (
    <div>
      <p className="mb-2 text-[11px] text-[#9dbdac]">
        {usingFixtures
          ? 'Fixture scorecard: hand-made predicted and actual times, not a calibrated replay.'
          : 'Predicted times are modelled. Actual times are recorded barrage peaks.'}
        {' '}Error is actual minus predicted: positive means the actual time is later than the prediction. Hours are Asia/Karachi.
      </p>
      {note && (
        <details className="mb-2 text-[11px] text-[#8aa898]">
          <summary className="cursor-pointer font-medium text-[#c5d9cc]">How this is scored</summary>
          <p className="mt-2 leading-relaxed">{note}</p>
        </details>
      )}
      <p className="mb-2 text-sm font-semibold text-slate-100">
        Wave 1 and Wave 2: {within24} of {list.length} crests within ±24 h
      </p>
      {list.length === 0 ? (
        <p className="text-sm text-[#9dbdac]">No scorecard for this replay.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-left text-xs tabular-nums whitespace-nowrap">
            <thead className="text-[10px] uppercase tracking-wide text-[#8aa898]">
              <tr>
                <th className="px-2 py-1 font-semibold">Barrage</th>
                <th className="px-2 py-1 font-semibold">Predicted</th>
                <th className="px-2 py-1 font-semibold">Actual</th>
                <th className="px-2 py-1 font-semibold">Error</th>
              </tr>
            </thead>
            <tbody>
              {list.map((row) => {
                const hours = Number(row.error_hours)
                const tone = !Number.isFinite(hours) || hours === 0 ? 'text-emerald-300' : 'text-amber-300'
                return (
                  <tr key={`${row.wave_id || 'wave'}-${row.barrage}`} className="border-t border-[#1b4a33]/60 hover:bg-[#0c2918]">
                    <td className="px-2 py-1 font-medium text-slate-100">
                      {row.barrage} <span className="font-normal text-[#8aa898]">· {waveName(row)}</span>
                      {row.in_sample === true && (
                        <span className="ml-1 rounded bg-amber-500/15 px-1 text-[9px] text-amber-300"
                          title="The reach lags were calibrated on this crest, so this row flatters the model.">
                          in-sample
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-slate-200"
                      title={row.predicted_low && row.predicted_high ? `Window: ${formatWall(row.predicted_low)} – ${formatWall(row.predicted_high)}` : undefined}>
                      {formatWall(row.predicted_time)}
                    </td>
                    <td className="px-2 py-1 text-slate-200">{formatWall(row.actual_peak_time)}</td>
                    <td className={`px-2 py-1 ${tone}`}>
                      {formatSignedHours(row.error_hours)}
                      {Number.isFinite(hours) && hours !== 0 && (
                        <span className="ml-1 text-[10px] text-[#8aa898]">{hours > 0 ? 'later' : 'earlier'}</span>
                      )}
                      {row.note && <sup className="ml-1 text-[#8aa898]" title={row.note}>*</sup>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {footnotes.length > 0 && (
        <p className="mt-2 text-[10px] leading-relaxed text-[#8aa898]">* {footnotes.join(' ')}</p>
      )}
    </div>
  )
}
