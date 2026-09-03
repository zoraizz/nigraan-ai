// Classification result display. Accepts the /classify-damage response body
// ({ damage_level, confidence, area }), a loading flag, or neither.
// Damage level gets the big instrument readout (Archivo, level color, left
// stripe); confidence is a mono readout with a flat meter.
const LEVEL_TEXT = {
  none: 'text-risk-low-bright',
  partial: 'text-risk-medium-bright',
  destroyed: 'text-risk-high-bright',
}

// Stripe color per damage level (same green/amber/red family as risk levels).
const DAMAGE_STRIPE = {
  none: 'var(--color-risk-low)',
  partial: 'var(--color-risk-medium)',
  destroyed: 'var(--color-risk-high)',
}

export default function DamageResultCard({ result, loading = false }) {
  const stripe = result ? DAMAGE_STRIPE[result.damage_level] : null
  const confidencePct = result ? Math.round(result.confidence * 100) : 0

  return (
    <div className="panel h-fit p-5">
      <h3 className="mb-4 font-heading text-[15px] font-semibold text-text">
        Classification result
      </h3>
      {loading ? (
        <div className="py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Running inference on the Damage Checker…</p>
        </div>
      ) : result ? (
        <div className="stripe-left pl-4" style={{ '--stripe': stripe }}>
          <p
            className={`font-heading text-3xl font-extrabold tracking-tight ${
              LEVEL_TEXT[result.damage_level] || 'text-text'
            }`}
          >
            {result.damage_level}
          </p>

          <dl className="mt-5 text-sm">
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Confidence</dt>
              <dd className="data text-text">
                {(result.confidence * 100).toFixed(1)}%
              </dd>
            </div>
            <div
              className="mt-1.5 h-1 overflow-hidden rounded-chip bg-surface-2"
              role="img"
              aria-label={`Confidence ${confidencePct}%`}
            >
              <div
                className="h-full rounded-chip"
                style={{ width: `${confidencePct}%`, backgroundColor: stripe }}
              />
            </div>
            <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-line pt-2.5">
              <dt className="text-muted">Area label</dt>
              <dd className="text-text">{result.area ?? 'n/a'}</dd>
            </div>
          </dl>
        </div>
      ) : (
        <p className="py-6 text-sm text-muted">
          No result yet. Select an image and run classification.
        </p>
      )}
    </div>
  )
}
