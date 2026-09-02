import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/risk-map', label: 'Risk Map' },
  { to: '/damage-assessment', label: 'Damage Assessment' },
  { to: '/aid-priority', label: 'Aid Priority' },
]

// Sidebar navigation between the 4 dashboard pages.
export default function Sidebar() {
  return (
    <aside className="flex w-56 flex-col bg-slate-900">
      <div className="px-4 py-5 text-lg font-bold text-white">Nigraan AI</div>
      <nav className="flex-1 space-y-1 px-2 py-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `block rounded px-3 py-2 text-sm ${
                isActive
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-3 text-xs text-slate-500">
        NDMA / PDMA decision support
      </div>
    </aside>
  )
}
