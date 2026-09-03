import { useEffect, useMemo, useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import ImageUploadBox from '../components/ImageUploadBox.jsx'
import DamageResultCard from '../components/DamageResultCard.jsx'
import { useDamageClassification } from '../hooks/useDamageClassification.js'
import { DISTRICT_NAMES } from '../config/districts.js'

// Image upload + classification result — live Damage Checker flow.
export default function DamageAssessment() {
  const [file, setFile] = useState(null)
  const [area, setArea] = useState('unknown')
  const { result, loading, error, classify, reset } = useDamageClassification()

  // Object URL for the local preview; revoked on change/unmount.
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
    <PageContainer
      title="Damage Assessment"
      lead="Upload a post-disaster satellite image tile to classify its damage severity (none / partial / destroyed) with the xBD-trained model."
    >
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="space-y-5">
          <ImageUploadBox
            previewUrl={previewUrl}
            fileName={file?.name ?? null}
            onFileSelect={handleFileSelect}
            onClassify={handleClassify}
            loading={loading}
            disabled={!file}
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
                Is the service running on http://127.0.0.1:8001? See
                dashboard/INTEGRATION.md.
              </p>
            </div>
          ) : null}
        </div>

        <DamageResultCard result={result} loading={loading} />
      </div>
    </PageContainer>
  )
}
