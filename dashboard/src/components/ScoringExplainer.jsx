// Transparency panel mirroring the Aid Priority module's scoring contract —
// authoritative source: aid-priority/scoring.py + API_CONTRACT.md. When the
// `scoring` metadata block from a live /rank-priority response is provided,
// its values (weights, maps, notes) are rendered instead of the defaults.
export default function ScoringExplainer({ scoring = null }) {
  const riskWeight = scoring?.risk_weight ?? 0.4
  const damageWeight = scoring?.damage_weight ?? 0.6
  const total = riskWeight + damageWeight

  return (
    <div className="panel p-4 text-sm text-muted">
      <h3 className="mb-2 font-heading text-[15px] font-semibold text-text">
        How priority is scored
      </h3>
      <p className="mb-3">
        <code className="data well px-1.5 py-0.5 text-xs text-text">
          priority = ({riskWeight} × risk + {damageWeight} × damage) / {total}
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
      </ul>
      {scoring ? (
        <p className="mt-2 text-xs text-muted">Tie-breaker: {scoring.tie_breaker}</p>
      ) : null}
    </div>
  )
}
