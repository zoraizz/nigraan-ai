import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import PageContainer from '../components/layout/PageContainer.jsx'
import ImageUploadBox from '../components/ImageUploadBox.jsx'
import DamageResultCard from '../components/DamageResultCard.jsx'
import SceneAssessment from '../components/SceneAssessment.jsx'
import GroundPhotosPanel from '../components/ground/GroundPhotosPanel.jsx'
import { useDamageClassification } from '../hooks/useDamageClassification.js'
import { DISTRICT_NAMES } from '../config/districts.js'

// One-click samples, served from public/sample-images/. The three satellite
// tiles come from damage-checker/sample-images/; the ground photo is not
// satellite imagery, so it shows the out-of-domain warning.
const SAMPLES = [
  { file: 'PAKISTAN-FLOODING_014695_post_disaster.png', label: 'Pakistan flood, 2022', type: 'image/png' },
  { file: 'PAKISTAN-FLOODING_018024_post_disaster.png', label: 'Pakistan flood, 2022 (intact)', type: 'image/png' },
  { file: 'joplin-tornado_00000120_post_disaster.png', label: 'Joplin tornado, USA', type: 'image/png' },
  { file: 'ground-photo-avalanche.jpg', label: 'Ground photo (not satellite)', type: 'image/jpeg' },
]

function SampleTiles({ onPick, disabled }) {
  return (
    <div className="panel p-4">
      <p className="mb-2 text-xs font-medium text-muted">Or try a sample</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SAMPLES.map((sample) => (
          <button
            key={sample.file}
            type="button"
            disabled={disabled}
            onClick={() => onPick(sample)}
            className="group overflow-hidden rounded-lg border border-line text-left hover:border-emerald-500/60 disabled:opacity-50"
          >
            <img
              src={`/sample-images/${sample.file}`}
              alt=""
              loading="lazy"
              className="aspect-square w-full object-cover"
            />
            <span className="block px-2 py-1.5 text-[11px] leading-snug text-muted group-hover:text-text">
              {sample.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

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

  const [sampleError, setSampleError] = useState(null)
  const handleSample = async (sample) => {
    reset()
    setSampleError(null)
    try {
      const response = await fetch(`/sample-images/${sample.file}`)
      if (!response.ok) throw new Error('not found')
      const picked = new File([await response.blob()], sample.file, { type: sample.type })
      setFile(picked)
      classify(picked, area === 'unknown' ? undefined : area)
    } catch {
      setSampleError('The sample image could not be loaded.')
    }
  }

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

        <SampleTiles onPick={handleSample} disabled={loading} />
        {sampleError ? <p className="text-sm text-risk-high-bright">{sampleError}</p> : null}

        <div className="panel p-4">
          <label
            htmlFor="area-select"
            className="mb-1.5 block text-xs font-medium text-muted"
          >
            District label (optional, does not change the result)
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
              The damage service may be waking up, which can take up to 60 seconds. Try again.
            </p>
          </div>
        ) : null}
      </div>

      <DamageResultCard result={result} loading={loading} />
    </div>
  )
}

const MODES = ['tile', 'scene', 'ground']

// The tab lives in the hash route query (#/damage-assessment?tab=ground), so
// links can open a tab directly and switch it when already on this page.
export default function DamageAssessment() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('tab')
  const mode = MODES.includes(requested) ? requested : 'tile'
  const setMode = (next) => setSearchParams(next === 'tile' ? {} : { tab: next }, { replace: true })

  return (
    <PageContainer
      title="Damage Assessment"
      lead="Rate building damage as none, partial or destroyed from satellite imagery, or add field photos for review."
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
        <button
          type="button"
          role="tab"
          id="mode-ground"
          aria-selected={mode === 'ground'}
          aria-controls="panel-ground"
          className={mode === 'ground' ? 'btn btn-primary' : 'btn'}
          onClick={() => setMode('ground')}
        >
          Ground photos
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
      <div
        id="panel-ground"
        role="tabpanel"
        aria-labelledby="mode-ground"
        hidden={mode !== 'ground'}
        className={mode === 'ground' ? undefined : 'hidden'}
      >
        <GroundPhotosPanel />
      </div>
    </PageContainer>
  )
}
