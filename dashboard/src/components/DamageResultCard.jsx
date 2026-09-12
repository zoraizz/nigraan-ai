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
  const isOod = result?.is_out_of_domain
  const stripe = isOod ? 'var(--color-risk-unknown)' : (result ? DAMAGE_STRIPE[result.damage_level] : null)
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
          {isOod && (
            <div className="mb-5 border-l-2 border-risk-medium pl-3">
              <div className="mb-2">
                <span className="warn-chip">Out of domain</span>
              </div>
              <p className="text-sm text-muted">{result.message}</p>
            </div>
          )}

          <p
            className={`font-heading text-3xl font-extrabold tracking-tight ${
              isOod ? 'text-muted opacity-60' : (LEVEL_TEXT[result.damage_level] || 'text-text')
            }`}
          >
            {result.damage_level}
          </p>
          
          {isOod && (
            <p className="mt-1 text-[11px] font-bold uppercase tracking-wider text-muted opacity-60">
              Raw model prediction (unreliable)
            </p>
          )}

          <dl className={`mt-5 text-sm ${isOod ? 'opacity-60' : ''}`}>
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
