// Ranked districts table for the Aid Priority page. Rows follow
// /rank-priority's ranked_districts entries.
export default function PriorityTable({ rows = [] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-400">
        No ranking data yet — run the demo scenario above.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Rank</th>
            <th className="px-4 py-3">District</th>
            <th className="px-4 py-3">Hazard</th>
            <th className="px-4 py-3">Risk</th>
            <th className="px-4 py-3">Damage Score</th>
            <th className="px-4 py-3">% Damaged</th>
            <th className="px-4 py-3">Tiles</th>
            <th className="px-4 py-3">Priority</th>
            <th className="px-4 py-3">Coverage</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.district} className="border-t border-slate-100">
              <td className="px-4 py-3 font-semibold text-slate-800">{row.rank}</td>
              <td className="px-4 py-3 font-medium text-slate-800">{row.district}</td>
              <td className="px-4 py-3">{row.hazard_type}</td>
              <td className="px-4 py-3">{row.risk_level}</td>
              <td className="px-4 py-3">{row.damage_score.toFixed(3)}</td>
              <td className="px-4 py-3">{(row.percent_damaged * 100).toFixed(0)}%</td>
              <td className="px-4 py-3">{row.tile_count}</td>
              <td className="px-4 py-3 font-semibold text-slate-900">
                {row.priority_score.toFixed(4)}
              </td>
              <td className="px-4 py-3">
                {row.low_coverage_warning ? (
                  <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                    ⚠ {row.low_coverage_warning}
                  </span>
                ) : (
                  <span className="text-xs text-slate-400">ok</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
