import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth.js'

function MenuIcon() {
  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

export default function Header({ toggleSidebar }) {
  const { user, isAuthenticated } = useAuth()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const clock = now.toLocaleTimeString('en-GB', {
    timeZone: 'Asia/Karachi',
    hour12: false,
  })

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between border-b border-[#1b4a33]/80 bg-[#071a0e]/90 px-4 backdrop-blur-md lg:px-6">
      <div className="flex items-center gap-3">
        {/* Hamburger 3-line sidebar toggle button */}
        <button
          onClick={toggleSidebar}
          type="button"
          aria-label="Toggle navigation menu"
          className="text-slate-300 hover:text-emerald-400 transition-colors cursor-pointer focus:outline-none p-1 shrink-0"
        >
          <MenuIcon />
        </button>
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-400">
        <a
          href="#home"
          className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400 hover:border-emerald-500/60 hover:bg-emerald-500/20 transition-colors"
        >
          ← Landing Page
        </a>
        <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-mono text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          PKT {clock}
        </span>
        <span className="hidden sm:inline text-slate-300 font-medium">
          {isAuthenticated ? (user ? user.name : 'Operator') : 'Guest'}
        </span>
      </div>
    </header>
  )
}

