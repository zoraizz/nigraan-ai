// Where a truncated /classify-scene response actually landed.
//
// damage-checker plans tiles in _plan_tiles: rows top to bottom, and within
// each row columns left to right (x increases to the right, y downward).
// Ragged edge tiles under half of tile_size are skipped and never appear
// in `tiles`. The time budget stops the loop before the next kept tile, so
// `tiles` is a prefix of that order. Counts and percent_damaged cover only
// that prefix.

export function describeSceneCoverage(scene) {
  if (!scene?.truncated) return null

  const processed = scene.tiles_processed ?? 0
  const total = scene.tiles_total ?? 0
  const lead = `processed ${processed} of ${total} tiles; the estimate covers only the processed tiles`
  const tiles = Array.isArray(scene.tiles) ? scene.tiles : []

  if (tiles.length === 0) {
    return (
      `${lead}. The service classifies kept tiles left to right, then top to bottom, `
      + 'from the top-left, and stopped before any tile finished, so none of the image was covered.'
    )
  }

  const last = tiles[tiles.length - 1]
  const rows = scene.grid?.rows
  const cols = scene.grid?.cols
  const at = rows && cols
    ? `row ${last.row + 1} of ${rows}, column ${last.col + 1} of ${cols}`
    : `row ${last.row + 1}, column ${last.col + 1}`

  return (
    `${lead}. The service classifies kept tiles left to right, then top to bottom, `
    + `from the top-left. This run stopped at ${at} (x ${last.x} px, y ${last.y} px), `
    + 'so the covered part is the top-left of the image through that tile. '
    + 'Tiles later in that order were not classified.'
  )
}
