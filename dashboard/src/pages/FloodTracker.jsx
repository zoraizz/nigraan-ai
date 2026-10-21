import { useEffect, useState } from 'react'
import AlertDrafts from '../components/flood/AlertDrafts.jsx'
import AtRiskTable from '../components/flood/AtRiskTable.jsx'
import EtaPanel from '../components/flood/EtaPanel.jsx'
import ReplayControls from '../components/flood/ReplayControls.jsx'
import ReplayScorecard from '../components/flood/ReplayScorecard.jsx'
import RiverMap from '../components/flood/RiverMap.jsx'
import { useFloodReplay } from '../hooks/useFloodReplay.js'
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

export default function FloodTracker() {
  useFloodFonts()
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
          Set VITE_FLOOD_USE_FIXTURES=true to use the bundled fixtures, or start the flood service and set VITE_FLOOD_API_URL.
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

      <details className="shrink-0 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2 text-xs text-[#c5d9cc]">
        <summary className="cursor-pointer font-semibold text-slate-200">Limitations</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>Estimates with ranges. Arrival times and village populations are modelled or estimated, not gauge readings.</li>
          <li>Gate operations and bund breaches are not modelled.</li>
          <li>Hill torrents and rain flooding are covered by Risk Flag.</li>
          <li>Supports, does not replace, official FFD warnings.</li>
        </ul>
      </details>

      <AlertDrafts
        village={selected}
        asOf={situation?.as_of}
        usingFixtures={replay.usingFixtures}
        onClose={() => setSelectedId(null)}
      />
    </div>
  )
}
