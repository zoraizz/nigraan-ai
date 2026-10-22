import { Link, NavLink } from 'react-router-dom'
import Logo from './Logo.jsx'

// Nav icons — 20px inline glyphs, stroke inherits currentColor.
function OverviewIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <rect x="2.5" y="2.5" width="6.5" height="6.5" rx="1.5" />
      <rect x="11" y="2.5" width="6.5" height="6.5" rx="1.5" />
      <rect x="2.5" y="11" width="6.5" height="6.5" rx="1.5" />
      <rect x="11" y="11" width="6.5" height="6.5" rx="1.5" />
    </svg>
  )
}

function RiskMapIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <circle cx="10" cy="10" r="6" />
      <path d="M10 2v3M10 15v3M2 10h3M15 10h3" />
      <circle cx="10" cy="10" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

function DamageIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
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

function FloodIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <path d="M2.5 7.5c1.6-1.8 3.2-1.8 4.8 0s3.2 1.8 4.8 0 3.2-1.8 4.8 0" />
      <path d="M2.5 12.5c1.6-1.8 3.2-1.8 4.8 0s3.2 1.8 4.8 0 3.2-1.8 4.8 0" />
    </svg>
  )
}

function GroundReportsIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <path d="M7.25 5.25 8.15 3.6h3.7l.9 1.65" />
      <rect x="3" y="5.25" width="14" height="10.25" rx="1.6" />
      <circle cx="10" cy="10.35" r="2.55" />
    </svg>
  )
}

function PriorityIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      <path d="M7.5 4.5H17M7.5 10H17M7.5 15.5H17" />
      <circle cx="4" cy="4.5" r="1.25" fill="currentColor" />
      <circle cx="4" cy="10" r="1.25" fill="currentColor" />
      <circle cx="4" cy="15.5" r="1.25" fill="currentColor" />
    </svg>
  )
}

const NAV_ITEMS = [
  { to: '/overview', label: 'Overview', icon: OverviewIcon },
  { to: '/risk-map', label: 'Risk Map', icon: RiskMapIcon },
  { to: '/damage-assessment', label: 'Damage Assessment', icon: DamageIcon },
  { to: '/aid-priority', label: 'Aid Priority', icon: PriorityIcon },
  // flood: River Flood Tracker
  { to: '/flood-tracker', label: 'Flood Tracker', icon: FloodIcon },
  // ground: Ground Reports
  { to: '/ground-reports', label: 'Ground Reports', icon: GroundReportsIcon },
]

export default function Sidebar({ isCollapsed }) {
  return (
    <aside
      className={`sticky top-0 flex h-screen shrink-0 flex-col overflow-y-auto border-r border-[#1b4a33]/80 bg-[#071a0e] transition-all duration-300 ${
        isCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Brand Header */}
      <Link
        to="/"
        aria-label="Nigraan AI home"
        className="flex h-14 items-center border-b border-[#1b4a33]/80 px-3 overflow-hidden"
      >
        <Logo size="sm" showText={!isCollapsed} />
      </Link>

      {/* Nav list */}
      <nav className="flex-1 space-y-1.5 p-2.5" aria-label="Primary Navigation">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={isCollapsed ? item.label : undefined}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
                  : 'text-slate-400 hover:bg-[#0a2418]/60 hover:text-slate-200 border border-transparent'
              } ${isCollapsed ? 'justify-center px-0' : ''}`
            }
          >
            {({ isActive }) => (
              <>
                <item.icon />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
                {isActive && !isCollapsed && (
                  <span className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#3ddc84]" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer version tag */}
      {!isCollapsed && (
        <div className="border-t border-[#1b4a33]/80 px-4 py-3 text-[11px] leading-snug text-[#6f8f7e]">
          <span className="font-semibold text-slate-400">Nigraan AI</span> v0.1 · Pakistan 2026
        </div>
      )}
    </aside>
  )
}

