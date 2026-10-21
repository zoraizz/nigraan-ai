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
      {labels && (
        <p className="mt-1 text-[11px] leading-snug text-[#8aa898]">
          <span className="mr-3"><span className="uppercase tracking-wide">Flows</span> {labels.flows}</span>
          <span className="mr-3"><span className="uppercase tracking-wide">ETAs</span> {labels.etas}</span>
          <span className="mr-3"><span className="uppercase tracking-wide">Villages</span> {labels.villages}</span>
          <span><span className="uppercase tracking-wide">Population</span> {labels.population}</span>
        </p>
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
    <div className="flex flex-col gap-3 lg:h-[calc(100vh-6.5rem)] lg:overflow-hidden">
      <Provenance situation={situation} usingFixtures={replay.usingFixtures} />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="h-full min-h-[460px] lg:col-span-2 lg:min-h-0">
          <RiverMap
            situation={situation}
            selectedVillageId={selectedId}
            onSelectVillage={setSelectedId}
          />
        </div>
        <div className="flex min-h-0 flex-col gap-3 lg:col-span-1">
          <EtaPanel etas={situation?.etas} />
          <AtRiskTable
            villages={villages}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
      </div>

      <section className="shrink-0 rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5">
        <ReplayControls
          steps={replay.steps}
          index={replay.index}
          playing={replay.playing}
          onScrub={replay.scrub}
          onTogglePlay={replay.togglePlay}
        />
        <details open className="mt-2 border-t border-[#1b4a33]/70 pt-2">
          <summary className="cursor-pointer text-xs font-semibold text-slate-200">Predicted vs actual</summary>
          <div className="pt-2">
            <ReplayScorecard rows={replay.scorecard} usingFixtures={replay.usingFixtures} />
          </div>
        </details>
      </section>

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
