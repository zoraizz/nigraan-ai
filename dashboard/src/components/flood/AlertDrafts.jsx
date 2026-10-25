import { useEffect, useState } from 'react'
import { draftTag } from '../../api/floodTracker.js'
import { useAlertDrafts } from '../../hooks/useAlertDrafts.js'
import { formatPeople, formatWall } from './timeFormat.js'

function copyWithExecCommand(text) {
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.left = '-9999px'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(area)
  if (!ok) throw new Error('copy failed')
}

async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise((_, reject) => {
          window.setTimeout(() => reject(new Error('clipboard timeout')), 400)
        }),
      ])
      return
    } catch {
      // The async clipboard API needs a focused document. Fall through.
    }
  }
  copyWithExecCommand(text)
}

function CopyButton({ label, text }) {
  const [state, setState] = useState('Copy')
  useEffect(() => {
    if (state === 'Copy') return undefined
    const id = window.setTimeout(() => setState('Copy'), 1500)
    return () => window.clearTimeout(id)
  }, [state])

  return (
    <button
      type="button"
      disabled={!text}
      onClick={async () => {
        try {
          await writeClipboard(text)
          setState('Copied')
        } catch {
          setState('Copy failed')
        }
      }}
      className="rounded-md border border-[#1b4a33] px-2 py-1 text-[11px] font-semibold text-slate-200 hover:border-emerald-500/50 disabled:opacity-40"
    >
      {state === 'Copy' ? label : state}
    </button>
  )
}

function DraftCard({ draft, sample }) {
  return (
    <article className="rounded-lg border border-[#1b4a33]/80 bg-[#04140c] p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-100">{draft.name || draft.village_id}</h3>
        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-300">
          {sample ? 'Sample draft' : draftTag(draft)}
        </span>
      </div>
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8aa898]">Urdu</p>
          <CopyButton label="Copy Urdu" text={draft.urdu || ''} />
        </div>
        <p dir="rtl" lang="ur" className="flood-urdu text-lg text-slate-100">{draft.urdu || '—'}</p>
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8aa898]">Sindhi</p>
          <CopyButton label="Copy Sindhi" text={draft.sindhi || ''} />
        </div>
        <p dir="rtl" lang="sd" className="flood-sindhi text-base text-slate-100">{draft.sindhi || '—'}</p>
      </div>
    </article>
  )
}

// context: optional { mode, scenario } so live and what-if drafts resolve
// villages against the same situation the page shows.
export default function AlertDrafts({ village, asOf, usingFixtures, onClose, context }) {
  const request = village
    ? { village_ids: [village.id], as_of: asOf || '', ...(context || {}) }
    : null
  const { drafts, loading, error } = useAlertDrafts(request)

  useEffect(() => {
    if (!village) return undefined
    function onKey(event) {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [village, onClose])

  if (!village) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/45">
      <button type="button" aria-label="Close alert draft" className="h-full flex-1 cursor-default" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="flood-draft-title"
        className="flex h-full w-full max-w-md flex-col border-l border-[#1b4a33] bg-[#071a0e] shadow-2xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-[#1b4a33]/80 px-4 py-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-400">Alert draft</p>
            <h2 id="flood-draft-title" className="text-lg font-semibold text-slate-100">{village.name}</h2>
            <p className="text-sm text-[#c5d9cc]">{village.district}</p>
            <p className="mt-1 font-mono text-[11px] text-[#9dbdac]">
              ETA ~{formatWall(village.eta)}
              {Number.isFinite(Number(village.hours_to_arrival)) ? ` · ${village.hours_to_arrival} h` : ''}
              {' · '}est. {formatPeople(village.population)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            autoFocus
            className="rounded-md border border-[#1b4a33] px-2 py-1 text-xs text-slate-200 hover:border-emerald-500/50"
          >
            Close
          </button>
        </header>
        <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-3">
          {usingFixtures && (
            <p className="text-[11px] text-amber-300/90">Sample draft. Hand-written example wording, not produced for this village or time step.</p>
          )}
          {loading && <p className="text-sm text-[#9dbdac]">Drafting…</p>}
          {error && <p className="text-sm text-red-300">{error.message}</p>}
          {!loading && !error && drafts.length === 0 && (
            <p className="text-sm text-[#c5d9cc]">No draft was returned for this village.</p>
          )}
          {drafts.map((draft) => (
            <DraftCard key={draft.village_id || draft.name} draft={draft} sample={usingFixtures} />
          ))}
        </div>
        <footer className="border-t border-[#1b4a33]/80 px-4 py-3 text-sm font-medium text-amber-200">
          Draft only. Nigraan never sends alerts.
        </footer>
      </aside>
    </div>
  )
}
