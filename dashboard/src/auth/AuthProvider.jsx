import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import { onOfficerUnauthorized, setOfficerPin, verifyOfficerPin } from '../api/groundIntake.js'

// Placeholder auth. Everyone stays isAuthenticated with no user, so other
// pages are unchanged. The only role switch is the Ground photos officer
// mode: a shared demo PIN (OFFICER_REVIEW_KEY on the Damage Checker), not
// real accounts. Real auth (e.g., NDMA/PDMA accounts) will be wired in here
// later; consumers already read this context via useAuth().
//
// role: "public" | "officer". Role and PIN live in sessionStorage so a
// reload keeps officer mode for this tab only.

const ROLE_KEY = 'nigraan.groundRole'
const PIN_KEY = 'nigraan.officerPin'
export const SESSION_ENDED_MESSAGE = 'Officer session ended, enter the PIN again'

const noop = () => {}

export const AuthContext = createContext({
  user: null,
  isAuthenticated: true,
  role: 'public',
  isOfficer: false,
  officerPin: null,
  notice: '',
  enterOfficerMode: async () => ({ ok: false, error: 'Officer mode is unavailable.' }),
  exitOfficerMode: noop,
  clearNotice: noop,
})

function readSession() {
  try {
    const role = sessionStorage.getItem(ROLE_KEY)
    const pin = sessionStorage.getItem(PIN_KEY)
    if (role === 'officer' && pin) return { role, pin }
  } catch {
    // Storage blocked: start as public.
  }
  return { role: 'public', pin: null }
}

function writeSession(role, pin) {
  try {
    if (role === 'officer' && pin) {
      sessionStorage.setItem(ROLE_KEY, role)
      sessionStorage.setItem(PIN_KEY, pin)
    } else {
      sessionStorage.removeItem(ROLE_KEY)
      sessionStorage.removeItem(PIN_KEY)
    }
  } catch {
    // Storage blocked: officer mode lasts until reload.
  }
}

export function AuthProvider({ children }) {
  // The API module needs the PIN before any child effect fetches, so the
  // restored PIN is handed over during the first render.
  const [session, setSession] = useState(() => {
    const restored = readSession()
    setOfficerPin(restored.pin)
    return restored
  })
  const [notice, setNotice] = useState('')

  const exitOfficerMode = useCallback(() => {
    setOfficerPin(null)
    writeSession('public', null)
    setSession({ role: 'public', pin: null })
  }, [])

  const enterOfficerMode = useCallback(async (candidate) => {
    const pin = String(candidate ?? '').trim()
    if (!pin) return { ok: false, error: 'Enter the PIN.' }
    try {
      await verifyOfficerPin(pin)
    } catch (err) {
      if (err?.status === 401) return { ok: false, error: 'Wrong PIN' }
      return { ok: false, error: err?.message || 'Could not check the PIN.' }
    }
    setOfficerPin(pin)
    writeSession('officer', pin)
    setSession({ role: 'officer', pin })
    setNotice('')
    return { ok: true }
  }, [])

  // A protected call answered 401 with the current PIN (e.g. the server's
  // PIN changed): drop back to field worker mode and say why.
  useEffect(() => onOfficerUnauthorized(() => {
    exitOfficerMode()
    setNotice(SESSION_ENDED_MESSAGE)
  }), [exitOfficerMode])

  const clearNotice = useCallback(() => setNotice(''), [])

  const value = useMemo(() => ({
    user: null,
    isAuthenticated: true,
    role: session.role,
    isOfficer: session.role === 'officer',
    officerPin: session.pin,
    notice,
    enterOfficerMode,
    exitOfficerMode,
    clearNotice,
  }), [session, notice, enterOfficerMode, exitOfficerMode, clearNotice])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
