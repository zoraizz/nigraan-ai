const COLUMNS = ['Rank', 'District', 'Hazard', 'Risk', 'Damage Score', 'Priority']

// Ranked districts table. Rows follow /rank-priority's ranked_districts
// entries; renders an empty state until live data is wired in.
export default function PriorityTable({ rows = [] }) {
  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            {COLUMNS.map((column) => (
              <th key={column} className="px-4 py-3">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={COLUMNS.length} className="px-4 py-8 text-center text-slate-400">
                No ranking data yet — Aid Priority integration lands with the hooks.
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.district} className="border-t border-slate-100">
                <td className="px-4 py-3">{row.rank}</td>
                <td className="px-4 py-3 font-medium text-slate-800">{row.district}</td>
                <td className="px-4 py-3">{row.hazard_type}</td>
                <td className="px-4 py-3">{row.risk_level}</td>
                <td className="px-4 py-3">{row.damage_score}</td>
                <td className="px-4 py-3 font-semibold">{row.priority_score}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
