import { useEffect, useState } from 'react'
import { describeSceneCoverage } from '../api/sceneCoverage.js'
import { sceneToPriority } from '../api/sceneToPriority.js'
import { DISTRICT_NAMES } from '../config/districts.js'
import { useSceneDamage } from '../scene/SceneDamageProvider.jsx'

const COUNT_LABELS = [
  ['none', 'None'],
  ['partial', 'Partial'],
  ['destroyed', 'Destroyed'],
  ['uncertain', 'Uncertain'],
]

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return 'n/a'
  return `${(Number(value) * 100).toFixed(2)}%`
}

export default function SceneBreakdown({ scene, loading = false }) {
  const { sceneDamage, setSceneDamage, clearSceneDamage } = useSceneDamage()
  const [district, setDistrict] = useState(DISTRICT_NAMES[0])
  const priorityEntry = scene ? sceneToPriority(scene) : null
  const coverage = scene ? describeSceneCoverage(scene) : null
  const counts = scene?.damage_breakdown ?? {}
  const uncertainCount = counts.uncertain ?? 0

  useEffect(() => {
    if (scene?.area && DISTRICT_NAMES.includes(scene.area)) {
      setDistrict(scene.area)
    }
  }, [scene])

  const storedForThis = Boolean(
    sceneDamage
    && priorityEntry
    && sceneDamage.district === district
    && sceneDamage.tile_count === priorityEntry.tile_count
    && sceneDamage.truncated === Boolean(scene?.truncated)
    && sceneDamage.damage_breakdown.none === priorityEntry.damage_breakdown.none
    && sceneDamage.damage_breakdown.partial === priorityEntry.damage_breakdown.partial
    && sceneDamage.damage_breakdown.destroyed === priorityEntry.damage_breakdown.destroyed,
  )

  const handleUse = (event) => {
    event.preventDefault()
    if (!priorityEntry || !district) return
    setSceneDamage({
      district,
      damage_breakdown: priorityEntry.damage_breakdown,
      tile_count: priorityEntry.tile_count,
      truncated: Boolean(scene.truncated),
    })
  }

  return (
    <div className="panel h-fit p-5">
      <h3 className="mb-4 font-heading text-[15px] font-semibold text-text">
        Scene breakdown
      </h3>

      {loading ? (
        <div className="py-10 text-center">
          <div className="spinner mx-auto mb-4" />
          <p className="text-sm text-muted">Classifying the scene…</p>
        </div>
      ) : scene ? (
        <>
          <dl className="space-y-2 text-sm">
            {COUNT_LABELS.map(([key, label]) => (
              <div key={key} className="flex items-baseline justify-between gap-4">
                <dt className="text-muted">{label}</dt>
                <dd className="data text-text">{counts[key] ?? 0}</dd>
              </div>
            ))}
            <div className="flex items-baseline justify-between gap-4 border-t border-line pt-2.5">
              <dt className="text-muted">percent damaged (tile-level estimate)</dt>
              <dd className="data text-text">{formatPercent(scene.percent_damaged)}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Skipped tiles</dt>
              <dd className="data text-text">{scene.skipped_count ?? 0}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-muted">Uncertain tiles</dt>
              <dd className="data text-text">{uncertainCount}</dd>
            </div>
          </dl>

          <p className="mt-3 text-xs leading-relaxed text-muted">
            Tile-level estimate. Each tile is labelled by its worst building,
            so percent damaged is not a building-level damage rate. Uncertain
            tiles were flagged out of domain and are left out of that percentage.
            {scene.skipped_count > 0
              ? ' Skipped tiles are a ragged edge under half the tile size; they are not drawn.'
              : ''}
          </p>

          {coverage ? (
            <p className="mt-3 text-sm leading-relaxed text-text">{coverage}</p>
          ) : null}

          {scene.truncated ? (
            <p className="mt-2">
              <span className="warn-chip">partial scene</span>
            </p>
          ) : null}

          {!priorityEntry ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-text">no usable tiles</p>
              {sceneDamage ? (
                <button type="button" className="btn" onClick={clearSceneDamage}>
                  Clear uploaded scene
                </button>
              ) : null}
            </div>
          ) : (
            <form className="mt-5 space-y-3 border-t border-line pt-4" onSubmit={handleUse}>
              <label htmlFor="scene-priority-district" className="block text-xs font-medium text-muted">
                Use in Aid Priority
              </label>
              <select
                id="scene-priority-district"
                name="district"
                className="field"
                value={district}
                onChange={(event) => setDistrict(event.target.value)}
              >
                {DISTRICT_NAMES.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <div className="flex flex-wrap gap-2">
                <button type="submit" className="btn btn-primary">
                  Use in Aid Priority
                </button>
                {sceneDamage ? (
                  <button type="button" className="btn" onClick={clearSceneDamage}>
                    Clear uploaded scene
                  </button>
                ) : null}
              </div>
              {storedForThis && sceneDamage ? (
                <p className="text-xs leading-relaxed text-ok-bright">
                  {`Stored for ${sceneDamage.district}. The next live ranking uses damage from uploaded scene for that district${sceneDamage.truncated ? ' (partial scene)' : ''}.`}
                </p>
              ) : sceneDamage ? (
                <p className="text-xs leading-relaxed text-muted">
                  {sceneDamage.district} currently holds an uploaded scene. Submitting
                  replaces it.
                </p>
              ) : (
                <p className="text-xs leading-relaxed text-muted">
                  Stores the tile counts for the district you pick. Aid Priority
                  applies them the next time the ranking runs.
                </p>
              )}
            </form>
          )}
        </>
      ) : (
        <p className="py-6 text-sm text-muted">
          No scene result yet. Choose an image and run classification.
        </p>
      )}
    </div>
  )
}
