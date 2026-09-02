// Transparency panel mirroring the Aid Priority module's scoring contract —
// authoritative source: aid-priority/scoring.py + API_CONTRACT.md. When the
// `scoring` metadata block from a live /rank-priority response is provided,
// its values (weights, maps, notes) are rendered instead of the defaults.
export default function ScoringExplainer({ scoring = null }) {
  const riskWeight = scoring?.risk_weight ?? 0.4
  const damageWeight = scoring?.damage_weight ?? 0.6
  const total = riskWeight + damageWeight

  return (
    <div className="rounded border border-slate-200 bg-white p-4 text-sm text-slate-600">
      <h3 className="mb-2 font-semibold text-slate-800">How priority is scored</h3>
      <p className="mb-2">
        <code className="rounded bg-slate-100 px-1 py-0.5">
          priority = ({riskWeight} × risk + {damageWeight} × damage) / {total}
        </code>
        {scoring ? (
          <span className="ml-2 text-xs text-slate-400">
            (live weights from the service)
          </span>
        ) : null}
      </p>
      <ul className="list-inside list-disc space-y-1">
        <li>risk: low 0.0 · medium 0.5 · high 1.0 · unknown 0.0</li>
        <li>damage: (0.5 × partial + 1.0 × destroyed) / classified tiles</li>
        <li>more photos never means more damage — damage is a per-tile rate</li>
        <li>low-coverage warnings are transparency signals, never scoring inputs</li>
      </ul>
      {scoring ? (
        <p className="mt-2 text-xs text-slate-400">
          Tie-breaker: {scoring.tie_breaker}
        </p>
      ) : null}
    </div>
  )
}
