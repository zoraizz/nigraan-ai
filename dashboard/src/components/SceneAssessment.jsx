import { useEffect, useMemo, useState } from 'react'
import ImageUploadBox from './ImageUploadBox.jsx'
import SceneOverlay from './SceneOverlay.jsx'
import SceneBreakdown from './SceneBreakdown.jsx'
import { useSceneClassification } from '../hooks/useSceneClassification.js'
import { DISTRICT_NAMES } from '../config/districts.js'
import { ENDPOINTS } from '../config/endpoints.js'

const TILE_SIZES = [256, 512, 1024]

function ServiceError({ title, error }) {
  if (!error) return null
  const code = error.body && typeof error.body.code === 'string' ? error.body.code : null
  const limitError = error.status === 413 || error.status === 422
  return (
    <div className="alert-error p-4 text-sm">
      <p className="font-semibold">{title}</p>
      <p className="mt-1">{error.message}</p>
      {limitError && code ? <p className="data mt-1 text-xs">{code}</p> : null}
      <p className="mt-2 text-xs">
        Damage Checker: <span className="data">{ENDPOINTS.damageApi}</span>
      </p>
    </div>
  )
}

export default function SceneAssessment({ active }) {
  const [file, setFile] = useState(null)
  const [area, setArea] = useState('unknown')
  const [tileSize, setTileSize] = useState(512)
  const { result, loading, error, wake, wakeError, classify, reset } = useSceneClassification(active)

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const handleFileSelect = (event) => {
    reset()
    setFile(event.target.files?.[0] || null)
  }

  const handleTileSize = (event) => {
    reset()
    setTileSize(Number(event.target.value))
  }

  const handleClassify = () => {
    classify(file, tileSize, area === 'unknown' ? undefined : area)
  }

  const waking = active && wake !== 'awake' && wake !== 'error'

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ImageUploadBox
          previewUrl={previewUrl}
          fileName={file?.name ?? null}
          onFileSelect={handleFileSelect}
          onClassify={handleClassify}
          loading={loading}
          disabled={!file}
          showPreview={false}
          actionLabel="Classify scene"
          loadingLabel="Classifying scene…"
          emptyText="No image selected yet. Choose a large post-disaster satellite image."
          inputId="scene-image"
        />

        <div className="panel space-y-4 p-4">
          <div>
            <label htmlFor="scene-tile-size" className="mb-1.5 block text-xs font-medium text-muted">
              Tile size
            </label>
            <select
              id="scene-tile-size"
              value={tileSize}
              onChange={handleTileSize}
              className="field"
            >
              {TILE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="scene-area-select" className="mb-1.5 block text-xs font-medium text-muted">
              Area / district label (optional passthrough)
            </label>
            <select
              id="scene-area-select"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              className="field"
            >
              <option value="unknown">unknown</option>
              {DISTRICT_NAMES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {waking ? (
        <div className="panel px-4 py-6 text-center">
          <div className="spinner mx-auto mb-3" />
          <p className="text-sm text-muted">
            Waking the service, the first request after idle can take about a minute.
          </p>
        </div>
      ) : null}

      <ServiceError title="Damage Checker did not respond" error={wake === 'error' ? wakeError : null} />
      <ServiceError title="Scene classification failed" error={error} />

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
        <SceneOverlay previewUrl={previewUrl} scene={result} loading={loading} />
        <SceneBreakdown scene={result} loading={loading} />
      </div>
    </div>
  )
}
