import { floodCategory } from '../../config/floodCategories.js'

export default function CategoryBadge({ category }) {
  const item = floodCategory(category)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] font-semibold leading-tight"
      style={{ backgroundColor: `${item.color}22`, color: item.color }}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
      {item.label}
    </span>
  )
}
