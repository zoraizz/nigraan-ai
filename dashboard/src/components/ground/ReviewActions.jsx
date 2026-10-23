import { useState } from 'react'
import { deleteGroundReport, reviewGroundReport } from '../../api/groundIntake.js'
import { DISTRICTS } from '../../config/districts.js'
import { DEPTHS, NEEDS, SCENES, words } from './groundLabels.js'

export default function ReviewActions({ report, refetch, onReviewed }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(null)
  const [note, setNote] = useState('')
  const [officer, setOfficer] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  // Delete removes the report and photo for good; reject keeps the record.
  async function remove() {
    setPending(true)
    setError('')
    setMessage('')
    try {
      await deleteGroundReport(report.id)
      refetch()
    } catch (err) {
      setError(err.message || 'Could not delete this report.')
      setPending(false)
    }
  }

  function startCorrection() {
    setDraft({ damage_level: report.damage_level, scene_type: report.scene_type, needs: [...(report.needs ?? [])], water: { ...report.water }, people: { ...report.people }, district: report.location?.district ?? '' })
    setEditing(true)
    setMessage('')
  }

  async function review(action) {
    setConfirmingDelete(false)
    setPending(true)
    setError('')
    setMessage('')
    try {
      const updated = await reviewGroundReport(report.id, { action, ...(action === 'correct' ? { corrections: draft } : {}), ...(note.trim() ? { note: note.trim() } : {}), ...(officer.trim() ? { officer: officer.trim() } : {}) })
      onReviewed?.(updated)
      refetch()
      setEditing(false)
      setNote('')
      setMessage('Review saved.')
    } catch (err) {
      setError(err.message || 'Could not save this review.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={(event) => { event.preventDefault(); review('correct') }}>
      <fieldset disabled={pending} className="space-y-3">
        <legend className="mb-3 text-sm font-semibold text-text">Officer review</legend>
        {editing && <div className="space-y-4 rounded-md border border-line bg-surface-2 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {[['damage_level', 'Damage level', ['none', 'partial', 'destroyed']], ['scene_type', 'Scene type', SCENES]].map(([key, label, options]) => <label key={key} className="text-xs text-muted">{label}<select className="field mt-1" value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}>{options.map((value) => <option key={value} value={value}>{words(value)}</option>)}</select></label>)}
            <label className="text-xs text-muted">Water depth<select className="field mt-1" value={draft.water.depth ?? 'none'} onChange={(event) => setDraft({ ...draft, water: { ...draft.water, depth: event.target.value, present: event.target.value !== 'none', flowing: event.target.value === 'none' ? false : Boolean(draft.water.flowing) } })}>{DEPTHS.map((depth) => <option key={depth} value={depth}>{words(depth)}</option>)}</select></label>
            <label className="text-xs text-muted">District<select className="field mt-1" value={draft.district} onChange={(event) => setDraft({ ...draft, district: event.target.value })}><option value="">Unknown</option>{draft.district && !DISTRICTS.some(({ name }) => name === draft.district) && <option value={draft.district}>{draft.district}</option>}{DISTRICTS.map(({ name }) => <option key={name}>{name}</option>)}</select></label>
          </div>
          <fieldset><legend className="mb-2 text-xs text-muted">Needs</legend><div className="flex flex-wrap gap-3">{NEEDS.map((need) => <label key={need} className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={draft.needs.includes(need)} onChange={(event) => setDraft({ ...draft, needs: event.target.checked ? [...draft.needs, need] : draft.needs.filter((value) => value !== need) })} />{words(need)}</label>)}</div></fieldset>
          <fieldset><legend className="mb-2 text-xs text-muted">People observed</legend><div className="flex flex-wrap gap-3">{['visible', 'stranded_or_trapped', 'on_rooftop', 'injured'].map((flag) => <label key={flag} className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={Boolean(draft.people[flag])} onChange={(event) => setDraft({ ...draft, people: { ...draft.people, [flag]: event.target.checked } })} />{words(flag)}</label>)}</div></fieldset>
          <label className="flex items-center gap-2 text-sm text-text"><input type="checkbox" disabled={draft.water.depth === 'none'} checked={Boolean(draft.water.flowing)} onChange={(event) => setDraft({ ...draft, water: { ...draft.water, flowing: event.target.checked } })} />Flowing water</label>
        </div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-muted">Note (optional)<textarea className="field mt-1" rows={2} value={note} onChange={(event) => setNote(event.target.value)} /></label>
          <label className="text-xs text-muted">Officer name (optional)<input className="field mt-1" value={officer} onChange={(event) => setOfficer(event.target.value)} /></label>
        </div>
        <div className="flex flex-wrap gap-2">
          {editing ? <><button className="btn btn-primary" type="submit">Save correction</button><button className="btn" type="button" onClick={() => setEditing(false)}>Cancel</button></> : <><button className="btn btn-primary" type="button" onClick={() => review('verify')}>Verify</button><button className="btn" type="button" onClick={startCorrection}>Correct</button><button className="btn text-risk-high-bright" type="button" onClick={() => review('reject')}>Reject</button><button className="ml-auto rounded-md px-3 py-1.5 text-sm text-muted hover:text-risk-high-bright" type="button" aria-expanded={confirmingDelete} onClick={() => { setConfirmingDelete(true); setMessage('') }}>Delete</button></>}
        </div>
        {confirmingDelete && !editing && <div className="rounded-md border border-risk-high p-3" role="alertdialog" aria-label="Confirm delete">
          <p className="text-sm text-text">Delete this report and its photo permanently? Use Reject instead to keep a record that it was false.</p>
          <div className="mt-3 flex flex-wrap gap-2"><button className="btn text-risk-high-bright" type="button" onClick={remove}>Delete</button><button className="btn" type="button" onClick={() => setConfirmingDelete(false)}>Keep</button></div>
        </div>}
      </fieldset>
      {pending && <p className="mt-2 text-sm text-muted" role="status">{confirmingDelete ? 'Deleting report…' : 'Saving review…'}</p>}
      {message && <p className="mt-2 text-sm text-emerald-400" role="status">{message}</p>}
      {error && <p className="alert-error mt-3 p-3 text-sm" role="alert">{error}</p>}
    </form>
  )
}
