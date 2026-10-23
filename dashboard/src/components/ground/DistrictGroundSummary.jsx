import { words } from './groundLabels.js'

// Sized to fit the panel without a horizontal scrollbar at 1280 px and up:
// short headings that may wrap, a narrow severity bar, top scenes one per
// line. overflow-x-auto stays only as a fallback for phone widths.
const HEADINGS = ['District', 'Reports', 'Verified', 'Severity', '% destroyed', 'Top scenes', 'Urgent', 'Sample']

export default function DistrictGroundSummary({ summary }) {
  const districts = Object.entries(summary?.districts ?? {})
  return (
    <section className="panel p-5" aria-labelledby="district-ground-title">
      <h2 id="district-ground-title" className="font-heading font-semibold text-text">District ground picture</h2>
      {!districts.length ? <p className="mt-3 text-sm text-muted">No district evidence yet.</p> : <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="mb-3 text-left text-xs text-muted">Unique, non-rejected reports. Severity: green = none, amber = partial, orange = destroyed.</caption>
          <thead className="border-b border-line text-xs text-muted"><tr>{HEADINGS.map((heading) => <th key={heading} scope="col" className="px-2 py-3 align-bottom font-medium">{heading}</th>)}</tr></thead>
          <tbody>{districts.map(([name, row]) => {
            const mix = row.severity_mix ?? {}
            const total = ['none', 'partial', 'destroyed'].reduce((sum, level) => sum + (mix[level] ?? 0), 0)
            const label = `None: ${mix.none ?? 0}, partial: ${mix.partial ?? 0}, destroyed: ${mix.destroyed ?? 0}`
            return <tr key={name} className="border-b border-line align-top text-text">
              <th scope="row" className="px-2 py-3 font-medium">{name}</th>
              <td className="data px-2 py-3">{row.report_count}</td><td className="data px-2 py-3">{row.verified_count}</td>
              <td className="w-24 px-2 py-3"><div className="flex h-1.5 w-20 overflow-hidden rounded bg-surface-2" role="img" aria-label={label} title={label}>{['none', 'partial', 'destroyed'].map((level) => <div key={level} style={{ width: `${total ? (mix[level] ?? 0) / total * 100 : 0}%`, backgroundColor: `var(--color-risk-${{ none: 'low', partial: 'medium', destroyed: 'high' }[level]})` }} />)}</div><p className="mt-1 whitespace-nowrap text-xs text-muted">{mix.none ?? 0} / {mix.partial ?? 0} / {mix.destroyed ?? 0}</p></td>
              <td className="data px-2 py-3">{Number.isFinite(row.share_destroyed) ? `${(row.share_destroyed * 100).toFixed(1)}%` : '—'}</td>
              <td className="px-2 py-3 text-xs">{row.top_scene_types?.length ? <ul className="space-y-0.5">{row.top_scene_types.map((scene) => <li key={scene.scene_type} className="capitalize">{words(scene.scene_type)} ({scene.count})</li>)}</ul> : '—'}</td>
              <td className="data px-2 py-3 text-risk-high-bright">{row.urgent_open}</td><td className="px-2 py-3">{row.low_sample_warning ? <span className="warn-chip whitespace-nowrap">Low sample</span> : <span className="text-xs text-muted">—</span>}</td>
            </tr>
          })}</tbody>
        </table>
      </div>}
      <p className="mt-4 text-xs leading-relaxed text-muted">Districts are compared by the share of severe reports, not by how many photos were sent.</p>
    </section>
  )
}
