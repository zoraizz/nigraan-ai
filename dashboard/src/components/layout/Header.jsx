import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/useAuth.js'
import Logo from './Logo.jsx'

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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface/80 backdrop-blur-md px-4 lg:px-6">
      <div className="flex items-center gap-3">
        <Logo size="sm" className="lg:hidden" />
        <h1 className="font-heading text-sm font-semibold tracking-tight text-text">
          Disaster Response Console
        </h1>
      </div>
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
