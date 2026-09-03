import { NavLink } from 'react-router-dom'

// Nav icons — 20px inline glyphs, stroke inherits currentColor.
function OverviewIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <circle cx="10" cy="10" r="7" />
      <path d="M3 10h14" />
      <ellipse cx="10" cy="10" rx="3" ry="7" />
    </svg>
  )
}

function RiskMapIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <circle cx="10" cy="10" r="5" />
      <path d="M10 1.5v3M10 15.5v3M1.5 10h3M15.5 10h3" />
      <circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

function DamageIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <path d="M3 6V4.5A1.5 1.5 0 0 1 4.5 3H6M14 3h1.5A1.5 1.5 0 0 1 17 4.5V6M17 14v1.5a1.5 1.5 0 0 1-1.5 1.5H14M6 17H4.5A1.5 1.5 0 0 1 3 15.5V14" />
      <path d="M6.5 13.5 9 10.2l1.8 2.2 1.4-1.7 2.3 2.8z" />
    </svg>
  )
}

function PriorityIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <path d="M7.5 4.5H17M7.5 10H17M7.5 15.5H17" />
      <rect x="3" y="3.4" width="2.2" height="2.2" fill="currentColor" stroke="none" />
      <rect x="3" y="8.9" width="2.2" height="2.2" fill="currentColor" stroke="none" />
      <rect x="3" y="14.4" width="2.2" height="2.2" fill="currentColor" stroke="none" />
    </svg>
  )
}

const NAV_ITEMS = [
  { to: '/', label: 'Overview', end: true, icon: OverviewIcon },
  { to: '/risk-map', label: 'Risk Map', icon: RiskMapIcon },
  { to: '/damage-assessment', label: 'Damage Assessment', icon: DamageIcon },
  { to: '/aid-priority', label: 'Aid Priority', icon: PriorityIcon },
]

// Persistent left rail. Icons only below lg (tooltip via title), icon + label
// from lg up. Active item is marked by a left accent bar, not a background pill.
export default function Sidebar() {
  return (
    <aside className="flex w-14 shrink-0 flex-col border-r border-line bg-surface lg:w-56">
      <div className="flex h-14 items-center gap-3 border-b border-line px-3 lg:px-4">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-chip border border-line-strong font-heading text-sm font-bold text-text">
          N
        </span>
        <span className="hidden min-w-0 leading-tight lg:block">
          <span className="block font-heading text-[15px] font-bold text-text">Nigraan</span>
          <span className="block text-[11px] text-muted">disaster operations</span>
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-2" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            title={item.label}
            className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
          >
            <item.icon />
            <span className="hidden lg:inline">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="hidden border-t border-line px-4 py-3 text-[11px] leading-snug text-muted lg:block">
        NDMA / PDMA decision support
      </div>
    </aside>
  )
}
