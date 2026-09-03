import { useAuth } from '../../auth/useAuth.js'

// Top bar — demonstrates the (no-op) auth wiring end to end.
export default function Header() {
  const { user, isAuthenticated } = useAuth()

  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
      <h1 className="text-lg font-semibold text-slate-800">
        Nigraan AI — Disaster Response Dashboard
      </h1>
      <span className="text-xs text-slate-400">
        {isAuthenticated ? (user ? user.name : 'Authenticated') : 'Not signed in'}
      </span>
    </header>
  )
}
