const LEVEL_COLORS = {
  none: 'text-green-700',
  partial: 'text-yellow-700',
  destroyed: 'text-red-700',
}

// Classification result display. Accepts the /classify-damage response body
// ({ damage_level, confidence, area }) or null while empty.
export default function DamageResultCard({ result }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-6">
      <h3 className="mb-3 font-semibold text-slate-800">Classification Result</h3>
      {result ? (
        <div>
          <p
            className={`text-2xl font-bold ${
              LEVEL_COLORS[result.damage_level] || 'text-slate-800'
            }`}
          >
            {result.damage_level}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            confidence: {(result.confidence * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-sm text-slate-500">area: {result.area}</p>
        </div>
      ) : (
        <p className="text-sm text-slate-400">
          No result yet — upload an image and run classification.
        </p>
      )}
    </div>
  )
}
