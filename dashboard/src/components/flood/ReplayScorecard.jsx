import { waveName } from '../../api/floodTracker.js'
import { formatSignedHours, formatWall } from './timeFormat.js'

export default function ReplayScorecard({ rows, note, usingFixtures }) {
  const list = Array.isArray(rows) ? rows : []
  return (
    <div>
      <p className="mb-2 text-[11px] text-[#9dbdac]">
        {usingFixtures
          ? 'Fixture scorecard: hand-made predicted and actual times, not a calibrated replay.'
          : 'Predicted times are modelled. Actual times are recorded barrage peaks.'}
        {' '}Error is actual minus predicted: positive means the actual time is later than the prediction. Hours are Asia/Karachi.
      </p>
      {note && <p className="mb-2 text-[11px] leading-snug text-[#8aa898]">{note}</p>}
      {list.length === 0 ? (
        <p className="text-sm text-[#9dbdac]">No scorecard for this replay.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-[#8aa898]">
              <tr>
                <th className="py-1 pr-3 font-semibold">Barrage</th>
                <th className="py-1 pr-3 font-semibold">Predicted</th>
                <th className="py-1 pr-3 font-semibold">Actual</th>
                <th className="py-1 font-semibold">Error</th>
              </tr>
            </thead>
            <tbody>
              {list.map((row) => {
                const hours = Number(row.error_hours)
                const tone = !Number.isFinite(hours) || hours === 0 ? 'text-emerald-300' : 'text-amber-300'
                return (
                  <tr key={`${row.wave_id || 'wave'}-${row.barrage}`} className="border-t border-[#1b4a33]/60">
                    <td className="py-1.5 pr-3 font-medium text-slate-100">
                      {row.barrage}
                      <span className="mt-0.5 block text-[10px] font-normal text-[#7f9c8c]">
                        {waveName(row)}
                        {row.in_sample === true && (
                          <span
                            className="ml-1.5 rounded bg-amber-500/15 px-1 text-amber-300"
                            title="The reach lags were calibrated on this crest, so this row flatters the model."
                          >
                            in-sample
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-slate-200">
                      {formatWall(row.predicted_time)}
                      {row.predicted_low && row.predicted_high && (
                        <span className="mt-0.5 block text-[10px] text-[#8aa898]">
                          {formatWall(row.predicted_low)} – {formatWall(row.predicted_high)}
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-slate-200">{formatWall(row.actual_peak_time)}</td>
                    <td className={`py-1.5 font-mono ${tone}`}>
                      {formatSignedHours(row.error_hours)}
                      {Number.isFinite(hours) && hours !== 0 && (
                        <span className="mt-0.5 block text-[10px] text-[#8aa898]">
                          {hours > 0 ? 'later than predicted' : 'earlier than predicted'}
                        </span>
                      )}
                      {row.note && (
                        <span className="mt-0.5 block max-w-[18rem] font-sans text-[10px] leading-snug text-[#8aa898]">{row.note}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
