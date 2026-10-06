// Turn a POST /classify-scene body into the damage fields of one
// POST /rank-priority district entry.
//
// /rank-priority accepts exactly one damage source. A scene uses
// damage_breakdown alone — never overall_damage_level in the same entry.
// That field means "worst class across tiles" here and "the one tile's
// label" on /rank-priority. uncertain is not part of DamageBreakdown.
// tile_count is classified tiles plus uncertain tiles (tiles the model
// finished). Skipped ragged edges and tiles cut off by the time budget
// are not included. Returns null when nothing was classified: /rank-priority
// requires at least one of none / partial / destroyed.

export function sceneToPriority(scene) {
  const counts = scene?.damage_breakdown
  if (!counts || typeof counts !== 'object') return null

  const none = Number(counts.none) || 0
  const partial = Number(counts.partial) || 0
  const destroyed = Number(counts.destroyed) || 0
  const uncertain = Number(counts.uncertain) || 0
  if (none + partial + destroyed < 1) return null

  return {
    damage_breakdown: { none, partial, destroyed },
    tile_count: none + partial + destroyed + uncertain,
  }
}
