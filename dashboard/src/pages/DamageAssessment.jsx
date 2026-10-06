import { useEffect, useMemo, useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import ImageUploadBox from '../components/ImageUploadBox.jsx'
import DamageResultCard from '../components/DamageResultCard.jsx'
import SceneAssessment from '../components/SceneAssessment.jsx'
import { useDamageClassification } from '../hooks/useDamageClassification.js'
import { DISTRICT_NAMES } from '../config/districts.js'
import { ENDPOINTS } from '../config/endpoints.js'

function TileAssessment() {
  const [file, setFile] = useState(null)
  const [area, setArea] = useState('unknown')
  const { result, loading, error, classify, reset } = useDamageClassification()

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const handleFileSelect = (event) => {
    reset()
    setFile(event.target.files?.[0] || null)
  }

  const handleClassify = () => classify(file, area === 'unknown' ? undefined : area)

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="space-y-5">
        <ImageUploadBox
          previewUrl={previewUrl}
          fileName={file?.name ?? null}
          onFileSelect={handleFileSelect}
          onClassify={handleClassify}
          loading={loading}
          disabled={!file}
          inputId="tile-image"
        />

        <div className="panel p-4">
          <label
            htmlFor="area-select"
            className="mb-1.5 block text-xs font-medium text-muted"
          >
            Area / district label (optional passthrough)
          </label>
          <select
            id="area-select"
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

        {error ? (
          <div className="alert-error p-4 text-sm">
            <p className="font-semibold">Classification failed</p>
            <p className="mt-1">{error.message}</p>
            <p className="mt-2 text-xs">
              Damage Checker: <span className="data">{ENDPOINTS.damageApi}</span>
            </p>
          </div>
        ) : null}
      </div>

      <DamageResultCard result={result} loading={loading} />
    </div>
  )
}

export default function DamageAssessment() {
  const [mode, setMode] = useState('tile')

  return (
    <PageContainer
      title="Damage Assessment"
      lead="Classify a single satellite tile, or a larger scene cut into tiles, as none / partial / destroyed."
    >
      <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Assessment mode">
        <button
          type="button"
          role="tab"
          id="mode-tile"
          aria-selected={mode === 'tile'}
          aria-controls="panel-tile"
          className={mode === 'tile' ? 'btn btn-primary' : 'btn'}
          onClick={() => setMode('tile')}
        >
          Single tile
        </button>
        <button
          type="button"
          role="tab"
          id="mode-scene"
          aria-selected={mode === 'scene'}
          aria-controls="panel-scene"
          className={mode === 'scene' ? 'btn btn-primary' : 'btn'}
          onClick={() => setMode('scene')}
        >
          Scene
        </button>
      </div>

      <div
        id="panel-tile"
        role="tabpanel"
        aria-labelledby="mode-tile"
        hidden={mode !== 'tile'}
        className={mode === 'tile' ? undefined : 'hidden'}
      >
        <TileAssessment />
      </div>
      <div
        id="panel-scene"
        role="tabpanel"
        aria-labelledby="mode-scene"
        hidden={mode !== 'scene'}
        className={mode === 'scene' ? undefined : 'hidden'}
      >
        <SceneAssessment active={mode === 'scene'} />
      </div>
    </PageContainer>
  )
}
