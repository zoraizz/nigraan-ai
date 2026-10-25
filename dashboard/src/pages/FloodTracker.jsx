import { useEffect, useState } from 'react'
import AlertDrafts from '../components/flood/AlertDrafts.jsx'
import AtRiskTable from '../components/flood/AtRiskTable.jsx'
import EtaPanel from '../components/flood/EtaPanel.jsx'
import ReplayControls from '../components/flood/ReplayControls.jsx'
import ReplayScorecard from '../components/flood/ReplayScorecard.jsx'
import RiverMap from '../components/flood/RiverMap.jsx'
import ForecastTable from '../components/flood/ForecastTable.jsx'
import OutlookCard from '../components/flood/OutlookCard.jsx'
import ScenarioImpact, { exposureLabel } from '../components/flood/ScenarioImpact.jsx'
import WhatIfForm from '../components/flood/WhatIfForm.jsx'
import { formatDay, formatPeople } from '../components/flood/timeFormat.js'
import { useFloodReplay } from '../hooks/useFloodReplay.js'
import { useLiveSituation } from '../hooks/useLiveSituation.js'
import { useWhatIf } from '../hooks/useWhatIf.js'
import '../components/flood/flood.css'

const FONT_HREF = 'https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@400;500;600;700&display=swap'

function useFloodFonts() {
  useEffect(() => {
    const id = 'nigraan-flood-fonts'
    if (document.getElementById(id)) return undefined
    const link = document.createElement('link')
    link.id = id
    link.rel = 'stylesheet'
    link.href = FONT_HREF
    document.head.appendChild(link)
    return undefined
  }, [])
}

function Provenance({ situation, usingFixtures }) {
  const labels = situation?.data_provenance
  return (
    <div className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-sm font-semibold text-slate-100">River Flood Tracker</h1>
        <p className="text-xs text-slate-200">2022 replay: real FFC barrage readings</p>
        {usingFixtures && (
          <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-amber-400">
            FIXTURE DATA
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-[#9dbdac]">
        Gauge readings: FFC Daily Flood Situation Reports, 2022 · ETAs: modelled from 2022 peak-to-peak lags · Population: WorldPop 2020
      </p>
      {labels && (
        <details className="mt-2 text-[11px] text-[#8aa898]">
          <summary className="cursor-pointer font-medium text-[#c5d9cc]">Data sources and method</summary>
          <div className="mt-2 space-y-1 leading-relaxed">
            {Object.entries(labels).map(([name, text]) => (
              <p key={name}><span className="capitalize font-semibold">{name}</span>: {text}</p>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function ReplayView() {
  const replay = useFloodReplay()
  const [selectedId, setSelectedId] = useState(null)
  const situation = replay.situation
  const villages = situation?.at_risk_villages ?? []
  const selected = villages.find((village) => village.id === selectedId) ?? null

  useEffect(() => {
    if (!selectedId) return
    const stillThere = villages.some((village) => village.id === selectedId)
    if (!stillThere) setSelectedId(null)
  }, [situation, selectedId, villages])

  if (replay.loading) {
    return (
      <div className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-4 py-6 text-sm text-[#c5d9cc]">
        Loading the 2022 replay…
      </div>
    )
  }

  if (replay.error) {
    return (
      <div className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-4 py-6 text-sm text-slate-200">
        <p className="font-semibold">Could not load the flood replay.</p>
        <p className="mt-1 text-[#c5d9cc]">{replay.error.message}</p>
        <p className="mt-2 text-[12px] text-[#9dbdac]">
          The flood service may be waking up, which can take up to 60 seconds. Reload the page to try again.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <Provenance situation={situation} usingFixtures={replay.usingFixtures} />

      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-3 lg:items-start">
        <div className="contents lg:col-span-2 lg:flex lg:min-w-0 lg:flex-col lg:gap-3">
          <div className="order-1 h-[380px] lg:h-[520px]">
            <RiverMap
              situation={situation}
              selectedVillageId={selectedId}
              onSelectVillage={setSelectedId}
            />
          </div>
          <section className="contents lg:order-2 lg:block lg:rounded-xl lg:border lg:border-[#1b4a33]/80 lg:bg-[#071a0e] lg:px-3 lg:py-2.5">
            <div className="order-2 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5 lg:border-0 lg:p-0">
              <ReplayControls
                steps={replay.steps}
                index={replay.index}
                playing={replay.playing}
                onScrub={replay.scrub}
                onTogglePlay={replay.togglePlay}
              />
            </div>
            <details open className="order-4 min-w-0 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5 lg:mt-2 lg:rounded-none lg:border-0 lg:border-t lg:px-0 lg:pb-0 lg:pt-2">
              <summary className="cursor-pointer text-xs font-semibold text-slate-200">Predicted vs actual</summary>
              <div className="pt-2">
                <ReplayScorecard rows={replay.scorecard} note={replay.scorecardNote} usingFixtures={replay.usingFixtures} />
              </div>
            </details>
          </section>
        </div>
        <div className="order-3 flex min-w-0 flex-col gap-3 lg:col-span-1">
          <EtaPanel etas={situation?.etas} />
          <AtRiskTable
            villages={villages}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
      </div>

      <section className="shrink-0 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2 text-xs text-[#c5d9cc]">
        <h2 className="font-semibold text-slate-200">Limitations</h2>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>Estimates with ranges. Arrival times and village populations are modelled or estimated, not gauge readings.</li>
          <li>Gate operations and bund breaches are not modelled.</li>
          <li>Hill torrents and rain flooding are covered by Risk Flag.</li>
          <li>Supports, does not replace, official FFD warnings.</li>
        </ul>
      </section>

      <AlertDrafts
        village={selected}
        asOf={situation?.as_of}
        usingFixtures={replay.usingFixtures}
        onClose={() => setSelectedId(null)}
      />
    </div>
  )
}

// flood: Today (live forecast) | 2022 replay | What-if. The replay stays the
// default for the demo; the last choice is remembered per browser.
const MODES = [
  { key: 'live', label: 'Today (live forecast)' },
  { key: 'replay', label: '2022 replay' },
  { key: 'what_if', label: 'What-if' },
]
const MODE_KEY = 'nigraan.flood.mode'

function readMode() {
  try {
    const saved = window.localStorage.getItem(MODE_KEY)
    return MODES.some((mode) => mode.key === saved) ? saved : 'replay'
  } catch {
    return 'replay'
  }
}

function saveMode(mode) {
  try {
    window.localStorage.setItem(MODE_KEY, mode)
  } catch {
    // Storage disabled: the toggle still works for this visit.
  }
}

function ModeToggle({ mode, onChange }) {
  return (
    <div role="group" aria-label="Flood tracker view" className="inline-flex w-fit flex-wrap rounded-lg border border-[#1b4a33] bg-[#04140c] p-0.5 text-xs">
      {MODES.map((item) => (
        <button key={item.key} type="button" aria-pressed={mode === item.key} onClick={() => onChange(item.key)}
          className={`rounded-md px-3 py-1.5 font-semibold ${mode === item.key
            ? 'bg-emerald-600 text-white'
            : 'text-[#c5d9cc] hover:bg-[#0c2918]'}`}>
          {item.label}
        </button>
      ))}
    </div>
  )
}

function Panel({ children }) {
  return (
    <div className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-4 py-6 text-sm text-[#c5d9cc]">{children}</div>
  )
}

function ModeHeader({ title, subtitle, situation, children }) {
  const labels = situation?.data_provenance
  return (
    <div className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-sm font-semibold text-slate-100">{title}</h1>
        <p className="text-xs text-slate-200">{subtitle}</p>
      </div>
      {children}
      {labels && (
        <details className="mt-2 text-[11px] text-[#8aa898]">
          <summary className="cursor-pointer font-medium text-[#c5d9cc]">Data sources and method</summary>
          <div className="mt-2 space-y-1 leading-relaxed">
            {Object.entries(labels).map(([name, text]) => (
              <p key={name}><span className="capitalize font-semibold">{name}</span>: {text}</p>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

// Map, downstream peaks, villages and the alert-draft drawer for one
// situation. `side` renders above the peaks; `below` under the map, either a
// node or a render function below({ selectedId, onSelect }) sharing the
// village selection (so a row there can open the alert draft).
function SituationView({ situation, side, below, draftContext }) {
  const [selectedId, setSelectedId] = useState(null)
  const villages = situation?.at_risk_villages ?? []
  const selected = villages.find((village) => village.id === selectedId) ?? null

  return (
    <>
      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-3 lg:items-start">
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          <div className="h-[380px] lg:h-[520px]">
            <RiverMap situation={situation} selectedVillageId={selectedId} onSelectVillage={setSelectedId} />
          </div>
          {typeof below === 'function' ? below({ selectedId, onSelect: setSelectedId }) : below}
        </div>
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-1">
          {side}
          <EtaPanel etas={situation?.etas} scenario={situation?.mode === 'what_if' ? situation?.scenario : null} />
          <AtRiskTable villages={villages} selectedId={selectedId} onSelect={setSelectedId} showDistance />
        </div>
      </div>
      <AlertDrafts
        village={selected}
        asOf={situation?.as_of}
        context={draftContext}
        onClose={() => setSelectedId(null)}
      />
    </>
  )
}

function LiveView({ onReplay, onRoute }) {
  const live = useLiveSituation(true)
  const situation = live.situation

  if (live.loading || (!situation && !live.error)) return <Panel>Loading today’s river forecast…</Panel>
  if (live.error) {
    return (
      <Panel>
        <p className="font-semibold text-slate-200">
          {live.unavailable ? 'Live forecast unavailable right now' : 'Could not load the live forecast.'}
        </p>
        <p className="mt-1 text-[12px] text-[#9dbdac]">{live.error.message}</p>
        <button type="button" onClick={onReplay} className="mt-2 text-sm font-semibold text-emerald-300 underline hover:text-emerald-200">
          Switch to the 2022 replay
        </button>
      </Panel>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <ModeHeader
        title="River Flood Tracker"
        subtitle={`As of ${formatDay(situation.as_of)} · modelled river forecast (GloFAS), not gauge readings`}
        situation={situation}
      />
      <SituationView
        situation={situation}
        draftContext={{ mode: 'live' }}
        side={<OutlookCard outlook={situation.outlook} forecastDays={situation.forecast_days} onRoute={onRoute} />}
        below={<ForecastTable rows={situation.forecast} warnings={situation.calibration_warnings} />}
      />
    </div>
  )
}

function WhatIfView({ prefill }) {
  const [body, setBody] = useState(null)
  const result = useWhatIf(body)
  const situation = result.situation
  const scenario = situation?.scenario
  const people = (situation?.at_risk_villages ?? []).reduce((sum, v) => sum + (Number(v.population) || 0), 0)

  return (
    <div className="flex flex-col gap-3">
      <ModeHeader
        title="What-if scenario"
        subtitle="Synthetic peak routed with the 2022 lags. Not a forecast."
        situation={situation}
      >
        {scenario && (
          <>
            <p className="mt-1 text-xs text-slate-200">
              {scenario.barrage} peak {formatPeople(Math.round(scenario.peak_cusecs))} cusecs ({scenario.peak_category}) on {formatDay(scenario.peak_time)}
              {situation.note ? '' : ` · est. ${formatPeople(people)} people in exposed villages downstream`}
            </p>
            <p className="mt-0.5 text-[11px] text-[#9dbdac]">Assumption: {scenario.assumption}</p>
            {exposureLabel(scenario.exposure) && (
              <p className="mt-0.5 text-[11px] text-slate-300">{exposureLabel(scenario.exposure)}</p>
            )}
            {situation.note && <p className="mt-0.5 text-[11px] text-amber-300">{situation.note}</p>}
          </>
        )}
      </ModeHeader>
      <WhatIfForm initial={prefill} onRun={setBody} running={result.loading} />
      {result.error && <Panel><span className="text-red-300">{result.error.message}</span></Panel>}
      {!body && !result.error && <Panel>Pick a barrage and a peak, then Run.</Panel>}
      {situation && (
        <SituationView
          situation={situation}
          draftContext={{ mode: 'what_if', scenario: body }}
          below={({ selectedId, onSelect }) => (
            <ScenarioImpact situation={situation} selectedId={selectedId} onSelect={onSelect} />
          )}
        />
      )}
    </div>
  )
}

export default function FloodTracker() {
  useFloodFonts()
  const [mode, setMode] = useState(readMode)
  const [prefill, setPrefill] = useState(null)

  function choose(next) {
    setMode(next)
    saveMode(next)
  }

  function routeForecast(row) {
    setPrefill({
      barrage: row.name,
      peak_cusecs: row.forecast_peak_cusecs,
      date: row.forecast_peak_date,
      key: `${row.name}-${row.forecast_peak_date}-${Date.now()}`,
    })
    choose('what_if')
  }

  return (
    <div className="flex flex-col gap-3">
      <ModeToggle mode={mode} onChange={choose} />
      {mode === 'live' && <LiveView onReplay={() => choose('replay')} onRoute={routeForecast} />}
      {mode === 'replay' && <ReplayView />}
      {mode === 'what_if' && <WhatIfView key={prefill?.key || 'blank'} prefill={prefill} />}
    </div>
  )
}
