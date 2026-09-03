import { useFlipReorder } from '../hooks/useFlipReorder.js'
import RiskBadge, { RISK_STRIPE } from './RiskBadge.jsx'
import HazardIcon from './HazardIcon.jsx'

// Ranked districts table for the Aid Priority page. Rows follow
// /rank-priority's ranked_districts entries. Rendered as a CSS-grid "table"
// (kept semantic with role attributes) so the FLIP hook can animate rows
// into place when the ranking loads or re-sorts.
const COLUMNS = [
  'Rank',
  'District',
  'Hazard',
  'Risk',
  'Damage score',
  '% damaged',
  'Tiles',
  'Priority',
  'Coverage',
]

export default function PriorityTable({ rows = [] }) {
  // Animate rows when the ranked list loads or re-sorts (district = key).
  // Must run before the empty-state return.
  const register = useFlipReorder(rows.map((row) => row.district))

  if (rows.length === 0) {
    return (
      <div className="panel px-4 py-10 text-center text-sm text-muted">
        No ranking data yet. Run the demo scenario above.
      </div>
    )
  }

  return (
    <div
      className="panel overflow-x-auto"
      role="table"
      aria-label="Districts ranked by aid priority"
    >
      <div className="ptable ptable-grid ptable-head" role="row">
        {COLUMNS.map((column) => (
          <div key={column} role="columnheader" className="px-3 py-2.5">
            {column}
          </div>
        ))}
      </div>
      <div role="rowgroup">
        {rows.map((row) => (
          <div
            key={row.district}
            ref={register(row.district)}
            role="row"
            className="ptable-grid ptable-row"
            style={{
              '--stripe': RISK_STRIPE[row.risk_level] || RISK_STRIPE.unknown,
            }}
          >
            <div role="cell" className="data px-3 py-3 font-semibold text-text">
              {String(row.rank).padStart(2, '0')}
            </div>
            <div role="cell" className="px-3 py-3 font-semibold text-text">
              {row.district}
            </div>
            <div role="cell" className="px-3 py-3">
              <HazardIcon hazard={row.hazard_type} />
            </div>
            <div role="cell" className="px-3 py-3">
              <RiskBadge level={row.risk_level} />
            </div>
            <div role="cell" className="data px-3 py-3 text-text">
              {row.damage_score.toFixed(3)}
            </div>
            <div role="cell" className="data px-3 py-3 text-text">
              {(row.percent_damaged * 100).toFixed(0)}%
            </div>
            <div role="cell" className="data px-3 py-3 text-muted">
              {row.tile_count}
            </div>
            <div role="cell" className="data px-3 py-3 text-base font-semibold text-text">
              {row.priority_score.toFixed(4)}
            </div>
            <div role="cell" className="px-3 py-3">
              {row.low_coverage_warning ? (
                <span className="warn-chip">{row.low_coverage_warning}</span>
              ) : (
                <span className="text-xs text-muted">ok</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
