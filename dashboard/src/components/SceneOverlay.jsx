import { useEffect, useRef, useState } from 'react'

// Grid painted in the uploaded image's own pixel space.
// Each tile is a percentage of the image element, so it tracks x/y/tile_size
// as the image scales. The wrapper shrinks to the img box (no object-fit
// letterbox), which keeps those percentages on the painted pixels.
// Kept edge tiles can be shorter than tile_size; skipped ragged edges are
// absent from `tiles` and stay undrawn.

const TILE_FILL = {
  none: 'color-mix(in srgb, var(--color-risk-low) 45%, transparent)',
  partial: 'color-mix(in srgb, var(--color-risk-medium) 48%, transparent)',
  destroyed: 'color-mix(in srgb, var(--color-risk-high) 50%, transparent)',
  uncertain: 'color-mix(in srgb, var(--color-risk-unknown) 38%, transparent)',
}

const TILE_FILL_HOT = {
  none: 'color-mix(in srgb, var(--color-risk-low) 65%, transparent)',
  partial: 'color-mix(in srgb, var(--color-risk-medium) 68%, transparent)',
  destroyed: 'color-mix(in srgb, var(--color-risk-high) 68%, transparent)',
  uncertain: 'color-mix(in srgb, var(--color-risk-unknown) 55%, transparent)',
}

const TILE_EDGE = {
  none: 'color-mix(in srgb, var(--color-risk-low) 85%, transparent)',
  partial: 'color-mix(in srgb, var(--color-risk-medium) 85%, transparent)',
  destroyed: 'color-mix(in srgb, var(--color-risk-high) 85%, transparent)',
  uncertain: 'var(--color-risk-unknown-bright)',
}

const LEGEND = [
  { label: 'none', fill: TILE_FILL.none, edge: TILE_EDGE.none },
  { label: 'partial', fill: TILE_FILL.partial, edge: TILE_EDGE.partial },
  { label: 'destroyed', fill: TILE_FILL.destroyed, edge: TILE_EDGE.destroyed },
  { label: 'uncertain', fill: TILE_FILL.uncertain, edge: TILE_EDGE.uncertain, dashed: true },
]

function tileBox(tile, tileSize, natural) {
  const widthPx = Math.min(tileSize, Math.max(0, natural.width - tile.x))
  const heightPx = Math.min(tileSize, Math.max(0, natural.height - tile.y))
  return {
    left: `${(tile.x / natural.width) * 100}%`,
    top: `${(tile.y / natural.height) * 100}%`,
    width: `${(widthPx / natural.width) * 100}%`,
    height: `${(heightPx / natural.height) * 100}%`,
  }
}

function tileReadout(tile) {
  const confidence = `${(tile.confidence * 100).toFixed(1)}%`
  if (tile.uncertain || tile.label === 'uncertain') {
    return `${tile.label} ${confidence} · out of domain`
  }
  return `${tile.label} ${confidence}`
}

export default function SceneOverlay({ previewUrl, scene, loading = false }) {
  const [natural, setNatural] = useState(null)
  const [activeKey, setActiveKey] = useState(null)
  const imgRef = useRef(null)

  useEffect(() => {
    setActiveKey(null)
    const img = imgRef.current
    if (img && img.complete && img.naturalWidth > 0) {
      setNatural({ width: img.naturalWidth, height: img.naturalHeight })
    } else {
      setNatural(null)
    }
  }, [previewUrl])

  const tiles = scene?.tiles ?? []
  const tileSize = scene?.tile_size
  const active = tiles.find((tile) => `${tile.row}-${tile.col}` === activeKey) ?? null

  return (
    <div className="panel p-4">
      <h3 className="mb-3 font-heading text-[15px] font-semibold text-text">
        Scene
      </h3>

      {previewUrl ? (
        <div className="relative inline-block max-w-full align-top">
          <img
            ref={imgRef}
            src={previewUrl}
            alt="Uploaded scene"
            className="block h-auto max-h-[32rem] w-auto max-w-full"
            onLoad={(event) => {
              setNatural({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })
            }}
          />
          {natural && tileSize && tiles.length > 0 ? (
            <div className="absolute inset-0" role="group" aria-label="Classified tiles">
              {tiles.map((tile) => {
                const key = `${tile.row}-${tile.col}`
                const uncertain = Boolean(tile.uncertain || tile.label === 'uncertain')
                const label = tile.label in TILE_FILL ? tile.label : 'uncertain'
                return (
                  <button
                    key={key}
                    type="button"
                    className={
                      uncertain
                        ? `scene-tile scene-tile-uncertain${activeKey === key ? ' scene-tile-active' : ''}`
                        : `scene-tile${activeKey === key ? ' scene-tile-active' : ''}`
                    }
                    style={{
                      ...tileBox(tile, tileSize, natural),
                      '--tile-fill': TILE_FILL[label],
                      '--tile-fill-hot': TILE_FILL_HOT[label],
                      '--tile-edge': TILE_EDGE[label],
                    }}
                    aria-label={`Row ${tile.row + 1}, column ${tile.col + 1}, ${tileReadout(tile)}`}
                    onMouseEnter={() => setActiveKey(key)}
                    onMouseLeave={() => setActiveKey((current) => (current === key ? null : current))}
                    onFocus={() => setActiveKey(key)}
                    onBlur={() => setActiveKey((current) => (current === key ? null : current))}
                  >
                    <span className="scene-tile-tip data">{tileReadout(tile)}</span>
                  </button>
                )
              })}
            </div>
          ) : null}
        </div>
      ) : (
        <p className="py-6 text-sm text-muted">
          The scene appears here after you choose an image.
        </p>
      )}

      {tiles.length > 0 ? (
        <>
          <p className="data mt-3 min-h-5 text-xs text-text">
            {active
              ? `row ${active.row + 1} col ${active.col + 1} · ${tileReadout(active)}`
              : 'Hover or focus a tile for its label and confidence.'}
          </p>
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {LEGEND.map((item) => (
              <li key={item.label} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5"
                  style={{
                    backgroundColor: item.fill,
                    border: `1px ${item.dashed ? 'dashed' : 'solid'} ${item.edge}`,
                  }}
                  aria-hidden="true"
                />
                {item.label}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {loading ? (
        <p className="mt-3 text-xs text-muted">Classifying tiles…</p>
      ) : null}
    </div>
  )
}
