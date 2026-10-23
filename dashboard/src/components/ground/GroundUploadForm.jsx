import { useEffect, useState } from 'react'
import { submitGroundPhoto } from '../../api/groundIntake.js'
import { DISTRICTS } from '../../config/districts.js'
import DamageResultCard from '../DamageResultCard.jsx'
import { LEVELS, NOT_DISASTER_MESSAGE, REJECTION_REASONS, SATELLITE_NOTE, words } from './groundLabels.js'

// Short confirmation for a ground report. Review happens in the officer queue,
// never here. onViewQueue is only passed in officer mode.
function ReportReceipt({ report, onViewQueue }) {
  return <div className="panel border-l-2 border-emerald-500 p-5" role="status">
    <p className="font-heading font-semibold text-text">Report received</p>
    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
      <span className="capitalize text-text">{words(report.scene_type)}</span>
      <span className={`rounded border px-2 py-0.5 text-xs capitalize ${LEVELS[report.damage_level] ?? 'text-muted'}`}>{words(report.damage_level)}</span>
      {report.urgent && <span className="rounded border border-red-500 bg-red-950/30 px-2 py-0.5 text-xs font-bold text-red-300">URGENT</span>}
    </div>
    <p className="mt-3 text-sm text-muted">An officer will review it.</p>
    {onViewQueue && <button type="button" className="btn mt-3" onClick={onViewQueue}>View in queue</button>}
  </div>
}

export default function GroundUploadForm({ refetch, onViewQueue }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [district, setDistrict] = useState('')
  const [village, setVillage] = useState('')
  const [reporterRole, setReporterRole] = useState('field_worker')
  const [location, setLocation] = useState(null)
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!file) { setPreview(''); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  function locate() {
    setLocationError('')
    if (!navigator.geolocation) { setLocationError('Location is not supported. Select a district manually.'); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      setLocation({ lat: coords.latitude, lon: coords.longitude })
      setLocating(false)
    }, () => {
      setLocationError('Could not access your location. Allow location access or select a district manually.')
      setLocating(false)
    }, { timeout: 15000, maximumAge: 0 })
  }
  async function submit(event) {
    event.preventDefault()
    if (!file || pending) return
    setPending(true)
    setError('')
    setResult(null)
    try {
      const response = await submitGroundPhoto(file, { district, village: village.trim(), reporterRole, ...location })
      if (!['satellite', 'ground', 'irrelevant'].includes(response?.route)) throw new Error('Unexpected response. Please try again.')
      setResult(response)
      if (response.route === 'ground') refetch?.()
    } catch (err) { setError(err.message || 'Could not read the photo.') }
    finally { setPending(false) }
  }
  return <div className="space-y-4">
    <section className="panel p-5" aria-labelledby="ground-upload-title">
      <h2 id="ground-upload-title" className="font-heading font-semibold text-text">Submit a ground photo</h2>
      <p className="mt-1 text-sm text-muted">Send one disaster photo for an AI reading and officer review.</p>
      <form onSubmit={submit} className="mt-4"><fieldset disabled={pending} className="space-y-4">
        <label className="block text-xs text-muted">Photo<input type="file" accept="image/*" required className="field mt-1" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); setError('') }} /></label>
        {preview && <img src={preview} alt="Selected photo preview" className="max-h-64 w-full rounded-md bg-surface-2 object-contain" />}
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-muted">District<select className="field mt-1" value={district} onChange={(event) => setDistrict(event.target.value)}><option value="">Unknown / select district</option>{DISTRICTS.map(({ name }) => <option key={name}>{name}</option>)}</select></label>
          <label className="text-xs text-muted">Village (optional)<input className="field mt-1" value={village} onChange={(event) => setVillage(event.target.value)} /></label>
          <label className="text-xs text-muted">Reporter role<select className="field mt-1" value={reporterRole} onChange={(event) => setReporterRole(event.target.value)}><option value="field_worker">Field worker</option><option value="rescue_team">Rescue team</option><option value="citizen">Citizen</option></select></label>
        </div>
        <div className="flex flex-wrap items-center gap-3"><button className="btn" type="button" disabled={locating} onClick={locate}>{locating ? 'Getting location…' : 'Use my location'}</button>{location && <><span className="data text-xs text-muted">{location.lat.toFixed(5)}, {location.lon.toFixed(5)}</span><button type="button" className="text-xs text-muted underline" onClick={() => setLocation(null)}>Remove location</button></>}</div>
        {locationError && <p className="text-sm text-risk-medium-bright" role="status">{locationError}</p>}
        <button type="submit" className="btn btn-primary" disabled={!file || locating}>Submit photo</button>
      </fieldset></form>
      {pending && <div className="mt-5 text-center" role="status"><div className="spinner mx-auto mb-3" /><p className="text-sm text-text">Reading the photo with Gemini</p><p className="mt-1 text-xs text-muted">A cold start can take up to a minute.</p></div>}
      {error && <div className="alert-error mt-4 p-4 text-sm" role="alert">{error}</div>}
    </section>
    {result?.route === 'satellite' && <div className="space-y-2"><p className="text-sm text-muted" role="status">{SATELLITE_NOTE}</p><DamageResultCard result={result.satellite} /></div>}
    {result?.route === 'ground' && <ReportReceipt report={result.report} onViewQueue={onViewQueue} />}
    {result?.route === 'irrelevant' && <div className="panel border-l-2 border-risk-medium p-5" role="status"><span className="warn-chip">Photo not accepted</span><p className="mt-3 text-sm text-text">{NOT_DISASTER_MESSAGE}</p><p className="mt-1 text-sm text-muted">{REJECTION_REASONS[result.reason] ?? REJECTION_REASONS.vlm_irrelevant}</p></div>}
  </div>
}
