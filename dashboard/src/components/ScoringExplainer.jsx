// Transparency panel mirroring the Aid Priority module's scoring contract —
// authoritative source: aid-priority/scoring.py + API_CONTRACT.md. When the
// `scoring` metadata block from a live /rank-priority response is provided,
// its values (weights, maps, notes) are rendered instead of the defaults.
export default function ScoringExplainer({ scoring = null, rows = [] }) {
  const riskWeight = scoring?.risk_weight ?? 0.4
  const damageWeight = scoring?.damage_weight ?? 0.6
  // flood: the River Flood Tracker term, present only when a district sent an ETA
  const flood = (scoring?.signals ?? []).find((signal) => signal.name === 'flood' && signal.active)
  const floodWeight = flood ? Number(flood.weight) || 0 : 0
  // ground: Ground Photo Intake term, shown only when a ranked district scored it
  const groundRows = rows.filter((row) => row.signals?.ground?.score != null)
  const groundSignal = (scoring?.signals ?? []).find((signal) => signal.name === 'ground')
  const ground = groundRows.length > 0 ? groundSignal : null
  const groundWeight = ground ? Number(ground.weight) || 0 : 0
  const total = Math.round((riskWeight + damageWeight + floodWeight + groundWeight) * 1000) / 1000

  return (
    <div className="panel p-4 text-sm text-muted">
      <h3 className="mb-2 font-heading text-[15px] font-semibold text-text">
        How priority is scored
      </h3>
      <p className="mb-3">
        <code className="data well px-1.5 py-0.5 text-xs text-text">
          priority = ({riskWeight} × risk + {damageWeight} × damage
          {flood ? ` + ${floodWeight} × flood` : ''}
          {ground ? ` + ${groundWeight} × ground` : ''}) / {total}
        </code>
        {scoring ? (
          <span className="ml-2 text-xs text-muted">(live weights from the service)</span>
        ) : null}
      </p>
      <ul className="list-inside list-disc space-y-1">
        <li>risk: low 0.0 · medium 0.5 · high 1.0 · unknown 0.0</li>
        <li>damage: (0.5 × partial + 1.0 × destroyed) / classified tiles</li>
        <li>more photos never means more damage: damage is a per-tile rate</li>
        <li>low-coverage warnings are transparency signals, never scoring inputs</li>
        {flood ? (
          <li>
            flood: hours until the river peak (River Flood Tracker estimate,
            not a gauge), scored {flood.curve || '1.0 up to 12 h, falling linearly to 0 at 120 h'};
            a district with no ETA scores 0
          </li>
        ) : null}
        {ground ? (
          <li>
            ground: {ground.curve}; a district without ground reports skips
            the term and its weight
            <ul className="ml-5 mt-1 space-y-0.5 text-xs">
              {groundRows.map((row) => {
                const evidence = row.signals.ground.value ?? {}
                const unique = (evidence.none ?? 0) + (evidence.partial ?? 0) + (evidence.destroyed ?? 0)
                return (
                  <li key={row.district}>
                    <span className="text-text">{row.district}</span>: based on{' '}
                    <span className="data">{unique}</span> unique ground{' '}
                    {unique === 1 ? 'report' : 'reports'} (
                    <span className="data">{evidence.verified_count ?? 0}</span> verified)
                  </li>
                )
              })}
            </ul>
          </li>
        ) : null}
      </ul>
      {scoring ? (
        <p className="mt-2 text-xs text-muted">Tie-breaker: {scoring.tie_breaker}</p>
      ) : null}
    </div>
  )
}
