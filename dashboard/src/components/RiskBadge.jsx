const STYLES = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-red-100 text-red-800',
  unknown: 'bg-slate-100 text-slate-600',
}

// Risk Flag's risk_level values: low | medium | high | unknown.
export default function RiskBadge({ level = 'unknown' }) {
  const style = STYLES[level] || STYLES.unknown
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {level}
    </span>
  )
}
