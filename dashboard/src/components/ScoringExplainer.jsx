// Transparency panel mirroring the Aid Priority module's scoring contract —
// the authoritative definition lives in aid-priority/scoring.py and
// API_CONTRACT.md. Weights shown here are the defaults (risk 0.4 / damage 0.6).
export default function ScoringExplainer() {
  return (
    <div className="rounded border border-slate-200 bg-white p-4 text-sm text-slate-600">
      <h3 className="mb-2 font-semibold text-slate-800">How priority is scored</h3>
      <p className="mb-2">
        <code className="rounded bg-slate-100 px-1 py-0.5">
          priority = (0.4 × risk + 0.6 × damage) / 1.0
        </code>
      </p>
      <ul className="list-inside list-disc space-y-1">
        <li>risk: low 0.0 · medium 0.5 · high 1.0 · unknown 0.0</li>
        <li>damage: (0.5 × partial + 1.0 × destroyed) / classified tiles</li>
        <li>more photos never means more damage — damage is a per-tile rate</li>
        <li>low-coverage warnings are transparency signals, never scoring inputs</li>
      </ul>
    </div>
  )
}
