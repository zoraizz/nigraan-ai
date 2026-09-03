import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth.js'

// Top bar — console identity, live PKT clock (a data readout, hence mono),
// and the (no-op) auth status wiring.
export default function Header() {
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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-4 lg:px-6">
      <h1 className="font-heading text-[15px] font-semibold tracking-tight text-text">
        Disaster Response Console
      </h1>
      <div className="flex items-center gap-4 text-xs text-muted">
        <span className="data" title="Pakistan Standard Time">
          PKT {clock}
        </span>
        <span className="hidden sm:inline">
          {isAuthenticated ? (user ? user.name : 'Authenticated') : 'Not signed in'}
        </span>
      </div>
    </header>
  )
}
