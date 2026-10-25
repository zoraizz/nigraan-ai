import { useState } from 'react'
import GroundUploadForm from './GroundUploadForm.jsx'
import GroundReportCard from './GroundReportCard.jsx'
import ReviewActions from './ReviewActions.jsx'
import UrgentBanner from './UrgentBanner.jsx'
import DistrictGroundSummary from './DistrictGroundSummary.jsx'
import { useAuth } from '../../auth/useAuth.js'
import { DISTRICTS } from '../../config/districts.js'
import { useGroundReports } from '../../hooks/useGroundReports.js'

// DEMO ONLY: remove the PIN hint after the hackathon
const DEMO_PIN_HINT = 'Demo officer PIN: 2026'

const TABS = [
  { key: 'queue', label: 'Review queue' },
  { key: 'district', label: 'District picture' },
  { key: 'submit', label: 'Submit photo' },
]

// Field worker | Officer. Officer opens an inline PIN form; the role only
// changes once the server accepts the PIN, but the highlight follows the
// click. Cancel, a failed PIN or Exit moves it back to Field worker.
function ModeSwitch() {
  const { isOfficer, enterOfficerMode, exitOfficerMode, notice, clearNotice } = useAuth()
  const [pinOpen, setPinOpen] = useState(false)
  const [pin, setPin] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')

  function chooseFieldWorker() {
    setPinOpen(false)
    setPin('')
    setError('')
    if (isOfficer) exitOfficerMode()
  }

  function chooseOfficer() {
    if (isOfficer) return
    clearNotice()
    setError('')
    setPinOpen(true)
  }

  async function submitPin(event) {
    event.preventDefault()
    if (checking) return
    setChecking(true)
    setError('')
    const result = await enterOfficerMode(pin)
    setChecking(false)
    setPinOpen(false)
    setPin('')
    // A failed PIN closes the form; the error stays under the toggle.
    if (!result.ok) setError(result.error)
  }

  const officerChosen = isOfficer || pinOpen
  const options = [
    { key: 'field_worker', label: 'Field worker', active: !officerChosen, onClick: chooseFieldWorker },
    { key: 'officer', label: 'Officer', active: officerChosen, onClick: chooseOfficer },
  ]
  return <div className="space-y-3">
    <div className="flex flex-wrap items-center gap-3">
      <div role="group" aria-label="Who is submitting" className="inline-flex w-fit flex-wrap rounded-lg border border-line bg-surface-2 p-0.5 text-sm">
        {options.map((item) => <button key={item.key} type="button" aria-pressed={item.active} onClick={item.onClick}
          className={`rounded-md px-3 py-1.5 font-semibold ${item.active ? 'bg-emerald-600 text-white' : 'text-muted hover:text-text'}`}>{item.label}</button>)}
      </div>
      {isOfficer && <><span className="rounded border border-emerald-500 px-2 py-0.5 text-xs font-semibold text-emerald-400">Officer mode</span><button type="button" className="btn" onClick={chooseFieldWorker}>Exit officer mode</button></>}
    </div>
    {notice && <div className="alert-error p-3 text-sm" role="alert">{notice}</div>}
    {error && !pinOpen && !isOfficer && <p className="text-sm text-risk-high-bright" role="alert">{error}</p>}
    {pinOpen && !isOfficer && <form onSubmit={submitPin} className="panel max-w-sm p-4"><fieldset disabled={checking} className="space-y-3">
      <label className="block text-xs text-muted">Officer PIN<input type="password" inputMode="numeric" autoComplete="off" autoFocus required className="field mt-1" value={pin} onChange={(event) => { setPin(event.target.value); setError('') }} /></label>
      <p className="text-xs text-muted">{DEMO_PIN_HINT}</p>
      <div className="flex flex-wrap gap-2"><button type="submit" className="btn btn-primary">{checking ? 'Checking…' : 'Enter officer mode'}</button><button type="button" className="btn" onClick={chooseFieldWorker}>Cancel</button></div>
    </fieldset></form>}
  </div>
}

// Mounted only in officer mode, so field workers never request the protected list.
function OfficerWorkspace() {
  const [tab, setTab] = useState('queue')
  const [district, setDistrict] = useState('')
  const { reports, summary, loading, error, refetch } = useGroundReports({ district })
  // Use the service's open-urgent definition; counts never feed a score here.
  const urgentCount = Object.values(summary?.districts ?? {}).reduce((sum, row) => sum + (row.urgent_open ?? 0), 0)

  const controls = <div className="flex flex-wrap items-end justify-between gap-3">
    <label className="text-xs text-muted">Filter by district<select className="field mt-1" value={district} onChange={(event) => setDistrict(event.target.value)}><option value="">All districts</option>{DISTRICTS.map(({ name }) => <option key={name}>{name}</option>)}</select></label>
    <button type="button" className="btn" onClick={refetch} disabled={loading}>Refresh reports</button>
  </div>
  const status = loading ? <div className="panel p-6 text-center" role="status"><div className="spinner mx-auto mb-3" /><p className="text-sm text-muted">Loading ground reports…</p></div>
    : error ? <div className="alert-error p-4 text-sm" role="alert"><p className="font-semibold">{error.status === 0 ? 'Damage Checker is not reachable' : 'Ground reports request failed'}</p><p className="mt-1">{error.message}</p><button type="button" className="btn mt-3" onClick={refetch}>Try again</button></div>
    : null

  return <div className="space-y-5">
    <UrgentBanner count={urgentCount} />
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Officer view">
      {TABS.map((item) => <button key={item.key} type="button" role="tab" id={`ground-tab-${item.key}`} aria-selected={tab === item.key} aria-controls={`ground-panel-${item.key}`}
        className={tab === item.key ? 'btn btn-primary' : 'btn'} onClick={() => setTab(item.key)}>{item.label}</button>)}
    </div>
    <div id={`ground-panel-${tab}`} role="tabpanel" aria-labelledby={`ground-tab-${tab}`} className="space-y-5">
      {tab === 'queue' && <>
        {controls}
        {status ?? <section aria-labelledby="ground-queue-title" className="space-y-4">
          <div><h2 id="ground-queue-title" className="font-heading text-lg font-semibold text-text">Review queue</h2><p className="mt-1 text-sm text-muted">{reports.filter((report) => report.status === 'unverified').length} awaiting review · Similar photos are folded into one report.</p></div>
          {reports.length ? reports.map((report) => <GroundReportCard key={report.id} report={report}><ReviewActions report={report} refetch={refetch} /></GroundReportCard>) : <p className="panel p-5 text-sm text-muted">No reports{district ? ` for ${district}` : ''} yet.</p>}
        </section>}
      </>}
      {tab === 'district' && <>
        {controls}
        {status ?? <DistrictGroundSummary summary={summary} />}
      </>}
      {tab === 'submit' && <GroundUploadForm asOfficer refetch={refetch} onViewQueue={() => setTab('queue')} />}
    </div>
  </div>
}

// Ground photos tab of Damage Assessment: field upload, or officer review
// behind the PIN. The urgent banner lives in OfficerWorkspace only.
export default function GroundPhotosPanel() {
  const { isOfficer } = useAuth()
  return <div className="space-y-5">
    <p className="text-sm text-muted">Ground-level disaster photos, structured observations, and officer review for local response.</p>
    <ModeSwitch />
    {isOfficer ? <OfficerWorkspace /> : <GroundUploadForm />}
  </div>
}
