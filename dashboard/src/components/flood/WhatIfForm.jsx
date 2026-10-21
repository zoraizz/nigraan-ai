import { useState } from 'react'

export const BARRAGES = ['Tarbela', 'Kalabagh', 'Chashma', 'Taunsa', 'Guddu', 'Sukkur', 'Kotri']
const PRESETS = [400000, 650000, 900000]
const MAX_CUSECS = 2000000

// initial: { barrage, peak_cusecs, date? } (date is YYYY-MM-DD). onRun gets the
// POST /what-if body; an empty date leaves peak_time to the server (today 06:00).
export default function WhatIfForm({ initial, onRun, running }) {
  const [barrage, setBarrage] = useState(initial?.barrage || 'Taunsa')
  const [peak, setPeak] = useState(String(Math.round(initial?.peak_cusecs || 650000)))
  const [date, setDate] = useState(initial?.date || '')
  const value = Number(peak)
  const valid = Number.isFinite(value) && value > 0 && value <= MAX_CUSECS

  function submit(event) {
    event.preventDefault()
    if (!valid) return
    const body = { barrage, peak_cusecs: value }
    if (date) body.peak_time = `${date}T06:00`
    onRun(body)
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5 text-xs">
      <label className="flex flex-col gap-1 text-[#9dbdac]">
        Barrage
        <select value={barrage} onChange={(e) => setBarrage(e.target.value)}
          className="rounded-md border border-[#1b4a33] bg-[#04140c] px-2 py-1 text-sm text-slate-100">
          {BARRAGES.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[#9dbdac]">
        Peak (cusecs)
        <input type="number" min={1} max={MAX_CUSECS} step={1000} value={peak} onChange={(e) => setPeak(e.target.value)}
          className="w-32 rounded-md border border-[#1b4a33] bg-[#04140c] px-2 py-1 text-sm tabular-nums text-slate-100" />
      </label>
      <div className="flex gap-1">
        {PRESETS.map((preset) => (
          <button key={preset} type="button" onClick={() => setPeak(String(preset))}
            className={`rounded-md border px-2 py-1 font-semibold ${Number(peak) === preset
              ? 'border-emerald-500/60 bg-emerald-500/15 text-emerald-200'
              : 'border-[#1b4a33] text-slate-300 hover:border-emerald-500/40'}`}>
            {preset / 1000}k
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1 text-[#9dbdac]">
        Peak date (optional)
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
          className="rounded-md border border-[#1b4a33] bg-[#04140c] px-2 py-1 text-sm text-slate-100 [color-scheme:dark]" />
      </label>
      <button type="submit" disabled={!valid || running}
        className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-40">
        {running ? 'Running…' : 'Run'}
      </button>
      {!valid && <p className="w-full text-red-300">Peak must be between 1 and 2,000,000 cusecs.</p>}
    </form>
  )
}
