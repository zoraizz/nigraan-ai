import { formatPeople, formatWall, parseWallTime } from './timeFormat.js'

// What-if impact under the map, computed client-side from the /what-if
// response: KPI tiles and villages grouped by district. Hours are measured
// from scenario.peak_time. Villages are those flooded in 2022 (exposure proxy).

function hoursAfter(peakTime, eta) {
  const peak = parseWallTime(peakTime)
  const at = parseWallTime(eta)
  if (peak == null || at == null) return null
  return Math.round((at - peak) / 3600000)
}

function formatDays(hours) {
  const days = Math.round((hours / 24) * 10) / 10
  return `+${days} ${days === 1 ? 'day' : 'days'}`
}

function byDistrict(villages) {
  const groups = new Map()
  villages.forEach((village) => {
    const key = village.district || 'Unknown'
    const group = groups.get(key) ?? { district: key, villages: 0, people: 0, first: null }
    group.villages += 1
    group.people += Number(village.population) || 0
    if (village.eta && (!group.first || village.eta < group.first.eta)) group.first = village
    groups.set(key, group)
  })
  return [...groups.values()].sort((a, b) => (a.first?.eta || '9999').localeCompare(b.first?.eta || '9999'))
}

// "Exposure: villages within 10 km of the river (Very High Flood)" from
// scenario.exposure; null below Medium Flood (the response note covers it).
export function exposureLabel(exposure) {
  if (!exposure) return null
  const category = exposure.category || ''
  if (exposure.radius_km == null) {
    return `Exposure: all 2022-flooded villages (${category.replace(/ Flood$/, '')})`
  }
  if (!(Number(exposure.radius_km) > 0)) return null
  return `Exposure: villages within ${Number(exposure.radius_km)} km of the river (${category})`
}

function Tile({ label, value, detail }) {
  return (
    <div className="min-w-0 rounded-lg border border-[#1b4a33]/80 bg-[#04140c] px-2 py-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[#8aa898]">{label}</p>
      <p className="truncate font-mono text-base text-slate-100">{value}</p>
      {detail && <p className="truncate text-[11px] text-[#9dbdac]">{detail}</p>}
    </div>
  )
}

export default function ScenarioImpact({ situation, selectedId, onSelect }) {
  const scenario = situation?.scenario
  if (!scenario) return null
  const villages = Array.isArray(situation.at_risk_villages) ? situation.at_risk_villages : []
  const empty = villages.length === 0
  const districts = byDistrict(villages)
  const people = districts.reduce((sum, d) => sum + d.people, 0)
  const maxPeople = Math.max(1, ...districts.map((d) => d.people))

  const kotri = (situation.etas ?? []).find((eta) => eta.barrage === 'Kotri')
  const kotriHours = kotri ? hoursAfter(scenario.peak_time, kotri.eta) : null
  const kotriDetail = kotri && kotriHours != null
    ? `${formatDays(kotriHours)} after the ${scenario.barrage} peak`
    : scenario.barrage === 'Kotri' ? 'Scenario peak is at Kotri' : null

  return (
    <section className="rounded-xl border border-[#1b4a33]/80 bg-[#071a0e] px-3 py-2.5">
      <h2 className="text-sm font-semibold text-slate-100">Scenario impact</h2>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile label="People at risk" value={empty ? '—' : formatPeople(people)} detail={empty ? null : 'Estimated population'} />
        <Tile label="Villages" value={empty ? '—' : formatPeople(villages.length)} />
        <Tile label="Districts" value={empty ? '—' : formatPeople(districts.length)} />
        <Tile label="Water reaches Kotri" value={kotri ? formatWall(kotri.eta) : '—'} detail={kotriDetail} />
      </div>
      {exposureLabel(scenario.exposure) && (
        <p className="mt-2 text-[11px] text-slate-300">{exposureLabel(scenario.exposure)}</p>
      )}
      {empty && situation.note && <p className="mt-2 text-[11px] text-amber-300">{situation.note}</p>}

      {!empty && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-[#1b4a33]/70">
          <p className="bg-[#0a2416] px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#8aa898]">Impact by district</p>
          <table className="w-full border-collapse text-left text-xs tabular-nums whitespace-nowrap">
            <thead className="bg-[#0a2416] text-[11px] uppercase tracking-wide text-[#8aa898]">
              <tr>
                <th className="px-2 py-1 font-semibold">District</th>
                <th className="px-2 py-1 font-semibold">First water</th>
                <th className="px-2 py-1 text-right font-semibold">Villages</th>
                <th className="px-2 py-1 text-right font-semibold">People</th>
              </tr>
            </thead>
            <tbody>
              {districts.map((d) => {
                const hours = d.first ? hoursAfter(scenario.peak_time, d.first.eta) : null
                const selected = d.first && d.first.id === selectedId
                const open = () => d.first && onSelect?.(d.first.id)
                return (
                  <tr
                    key={d.district}
                    tabIndex={0}
                    aria-selected={selected}
                    aria-label={`Open alert draft for the first village in ${d.district}`}
                    onClick={open}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        open()
                      }
                    }}
                    className={`cursor-pointer border-t border-[#1b4a33]/60 outline-none focus-visible:bg-emerald-500/15 ${
                      selected ? 'bg-emerald-500/10' : 'hover:bg-[#0c2918]'
                    }`}
                  >
                    <td className="px-2 py-1 font-medium text-slate-100">{d.district}</td>
                    <td className="px-2 py-1 text-slate-100" title={d.first ? `First village: ${d.first.name}` : undefined}>
                      {d.first ? formatWall(d.first.eta) : '—'}
                      {hours != null && <span className="text-[#9dbdac]"> · +{hours} h after peak</span>}
                    </td>
                    <td className="px-2 py-1 text-right text-slate-200">{formatPeople(d.villages)}</td>
                    <td className="relative px-2 py-1 text-right text-slate-100">
                      <span aria-hidden="true" className="absolute inset-y-1 right-0 rounded-l bg-emerald-500/20"
                        style={{ width: `${(d.people / maxPeople) * 100}%` }} />
                      <span className="relative">{formatPeople(d.people)}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-[#7f9c8c]">
        Hours are measured from the {scenario.barrage} peak. Village list = villages flooded in 2022 (exposure proxy).
      </p>
    </section>
  )
}
