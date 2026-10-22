export default function UrgentBanner({ count }) {
  if (!count) return null
  return (
    <div className="rounded-lg border border-red-500 bg-red-950/30 p-4 text-red-300" role="status">
      <p className="font-heading font-bold">URGENT · {count} open {count === 1 ? 'report' : 'reports'}</p>
      <p className="mt-1 text-sm">Prioritise these reports for officer review and response.</p>
    </div>
  )
}
