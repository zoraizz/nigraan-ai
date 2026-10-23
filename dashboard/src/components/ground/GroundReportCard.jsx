import { groundPhotoUrl } from '../../api/groundIntake.js'
import { LEVELS, ROLES, words } from './groundLabels.js'

const STATUS = { unverified: 'AI only, unverified', verified: 'Verified by officer', corrected: 'Corrected', rejected: 'Rejected' }

export default function GroundReportCard({ report, children }) {
  const location = report.location ?? {}
  const coordinates = Number.isFinite(location.lat) && Number.isFinite(location.lon)
  const people = report.people ?? {}
  const animals = report.animals ?? {}
  return (
    <article className="panel overflow-hidden">
      <div className="flex flex-col gap-4 p-5 sm:flex-row">
        <a href={groundPhotoUrl(report.id)} target="_blank" rel="noreferrer" className="shrink-0" aria-label="Open report photo">
          <img src={groundPhotoUrl(report.id)} alt={`Reported ${words(report.scene_type)}`} loading="lazy" className="h-40 w-full rounded-md bg-surface-2 object-cover sm:w-44" />
        </a>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-lg font-semibold capitalize text-text">{words(report.scene_type)}</h3>
            <span className={`rounded border px-2 py-0.5 text-xs capitalize ${LEVELS[report.damage_level] ?? 'text-muted'}`}>{report.damage_level}</span>
            <span className="rounded bg-surface-2 px-2 py-1 text-xs text-muted">{STATUS[report.status] ?? words(report.status)}</span>
            {report.duplicate_count > 0 && <span className="text-xs text-muted">+{report.duplicate_count} similar</span>}
          </div>
          {report.urgent && <div className="border-l-2 border-risk-high pl-3 text-sm text-risk-high-bright"><strong>URGENT</strong><ul className="mt-1 list-inside list-disc">{(report.urgent_reasons ?? []).map((reason) => <li key={reason}>{words(reason)}</li>)}</ul></div>}
          <p className="text-sm leading-relaxed text-text">{report.summary}</p>
          <div className="space-y-1 text-sm text-muted">
            <p>Water: {report.water?.present ? `${words(report.water.depth)} depth${report.water.flowing ? ', flowing' : ''}` : 'not observed'}</p>
            <p>People: {people.visible ? `visible${people.count_estimate != null ? ` (about ${people.count_estimate})` : ''}` : 'not observed'}{people.stranded_or_trapped && ' · stranded or trapped'}{people.on_rooftop && ' · on rooftop'}{people.injured && ' · injured'}</p>
            <p>Livestock: {animals.livestock_visible ? 'visible' : 'not observed'}{animals.livestock_at_risk && ' · at risk'}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs"><span className="text-muted">Needs:</span>{report.needs?.length ? report.needs.map((need) => <span key={need} className="rounded border border-line bg-surface-2 px-2 py-1 capitalize text-text">{words(need)}</span>) : <span className="text-muted">None observed</span>}</div>
          <div className="text-xs leading-relaxed text-muted">
            <p>{[location.district, location.village].filter(Boolean).join(' · ') || (!coordinates ? 'location unknown' : 'District unknown')} · Source: {words(location.source)}</p>
            {coordinates && <a className="text-emerald-400 underline" href={`https://www.openstreetmap.org/?mlat=${location.lat}&mlon=${location.lon}#map=16/${location.lat}/${location.lon}`} target="_blank" rel="noreferrer">{location.lat}, {location.lon} · OpenStreetMap</a>}
            <p className="mt-2">Reported by {ROLES[report.reporter_role] ?? words(report.reporter_role)} · Confidence: {Number.isFinite(report.confidence) ? `${Math.round(report.confidence * 100)}%` : 'unknown'} · Read by {report.vlm_source || 'unknown'}</p>
          </div>
        </div>
      </div>
      {children && <div className="border-t border-line p-5">{children}</div>}
    </article>
  )
}
