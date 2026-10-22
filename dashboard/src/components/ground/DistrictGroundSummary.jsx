import { words } from './groundLabels.js'

export default function DistrictGroundSummary({ summary }) {
  const districts = Object.entries(summary?.districts ?? {})
  return (
    <section className="panel p-5" aria-labelledby="district-ground-title">
      <h2 id="district-ground-title" className="font-heading font-semibold text-text">District ground picture</h2>
      {!districts.length ? <p className="mt-3 text-sm text-muted">No district evidence yet.</p> : <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="mb-3 text-left text-xs text-muted">Unique, non-rejected reports. Severity: green = none, amber = partial, orange = destroyed.</caption>
          <thead className="border-b border-line text-xs text-muted"><tr>{['District', 'Reports', 'Verified', 'Severity mix', 'Share destroyed', 'Top scenes', 'Urgent', 'Coverage'].map((heading) => <th key={heading} scope="col" className="whitespace-nowrap px-3 py-3">{heading}</th>)}</tr></thead>
          <tbody>{districts.map(([name, row]) => {
            const mix = row.severity_mix ?? {}
            const total = ['none', 'partial', 'destroyed'].reduce((sum, level) => sum + (mix[level] ?? 0), 0)
            const label = `None: ${mix.none ?? 0}, partial: ${mix.partial ?? 0}, destroyed: ${mix.destroyed ?? 0}`
            return <tr key={name} className="border-b border-line text-text">
              <th scope="row" className="px-3 py-3 font-medium">{name}</th>
              <td className="data px-3 py-3">{row.report_count}</td><td className="data px-3 py-3">{row.verified_count}</td>
              <td className="min-w-36 px-3 py-3"><div className="flex h-2 overflow-hidden rounded bg-surface-2" role="img" aria-label={label} title={label}>{['none', 'partial', 'destroyed'].map((level) => <div key={level} style={{ width: `${total ? (mix[level] ?? 0) / total * 100 : 0}%`, backgroundColor: `var(--color-risk-${{ none: 'low', partial: 'medium', destroyed: 'high' }[level]})` }} />)}</div><p className="mt-1 text-xs text-muted">{mix.none ?? 0} / {mix.partial ?? 0} / {mix.destroyed ?? 0}</p></td>
              <td className="data px-3 py-3">{Number.isFinite(row.share_destroyed) ? `${(row.share_destroyed * 100).toFixed(1)}%` : '—'}</td>
              <td className="px-3 py-3 text-xs">{row.top_scene_types?.map((scene) => `${words(scene.scene_type)} (${scene.count})`).join(', ') || '—'}</td>
              <td className="data px-3 py-3 text-risk-high-bright">{row.urgent_open}</td><td className="px-3 py-3">{row.low_sample_warning ? <span className="warn-chip">Low sample</span> : <span className="text-xs text-muted">—</span>}</td>
            </tr>
          })}</tbody>
        </table>
      </div>}
      <p className="mt-4 text-xs leading-relaxed text-muted">Districts are compared by the share of severe reports, not by how many photos were sent.</p>
    </section>
  )
}
