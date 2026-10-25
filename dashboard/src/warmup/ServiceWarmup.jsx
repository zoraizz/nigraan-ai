import { createContext, useContext, useEffect, useState } from 'react'
import { SERVICES, pingService } from '../api/health.js'
import { FLOOD_USE_FIXTURES } from '../api/floodTracker.js'

// Service warm-up: on first app load, ping every service's health route in
// parallel, retrying until it answers or WARMUP_TIMEOUT_MS passes. Failures
// are silent; consumers read the per-service status:
//   'pending' | 'up' | 'timeout' | 'skipped' (flood in fixture mode)
//   useServicesReady(keys) -> { ready, failed: [label], pending: [label] }
export const WARMUP_TIMEOUT_MS = 90000
const RETRY_MS = 5000
const ATTEMPT_MS = 30000

const WarmupContext = createContext(null)

function initialStatus() {
  return Object.fromEntries(SERVICES.map((service) => [
    service.key,
    service.key === 'flood' && FLOOD_USE_FIXTURES ? 'skipped' : 'pending',
  ]))
}

export function ServiceWarmupProvider({ children }) {
  const [status, setStatus] = useState(initialStatus)

  useEffect(() => {
    let active = true
    const started = Date.now()
    const timers = []
    const controllers = []
    const mark = (key, value) => setStatus((current) => ({ ...current, [key]: value }))

    SERVICES.forEach((service) => {
      if (service.key === 'flood' && FLOOD_USE_FIXTURES) return
      const attempt = async () => {
        const remaining = WARMUP_TIMEOUT_MS - (Date.now() - started)
        const controller = new AbortController()
        controllers.push(controller)
        const abortTimer = window.setTimeout(() => controller.abort(), Math.min(ATTEMPT_MS, Math.max(remaining, 0)))
        try {
          await pingService(service, controller.signal)
          if (active) mark(service.key, 'up')
          return
        } catch {
          // Silent: a sleeping instance answers with errors until it is up.
        } finally {
          window.clearTimeout(abortTimer)
        }
        if (!active) return
        if (Date.now() - started >= WARMUP_TIMEOUT_MS) {
          mark(service.key, 'timeout')
          return
        }
        timers.push(window.setTimeout(attempt, RETRY_MS))
      }
      attempt()
    })

    return () => {
      active = false
      timers.forEach((id) => window.clearTimeout(id))
      controllers.forEach((controller) => controller.abort())
    }
  }, [])

  return (
    <WarmupContext.Provider value={status}>
      {children}
      <WarmupIndicator status={status} />
    </WarmupContext.Provider>
  )
}

function WarmupIndicator({ status }) {
  const pending = SERVICES.filter((service) => status[service.key] === 'pending')
  if (pending.length === 0) return null
  const tracked = SERVICES.filter((service) => status[service.key] !== 'skipped')
  const answered = tracked.length - pending.length
  return (
    <div
      role="status"
      title={`Waiting for: ${pending.map((service) => service.label).join(', ')}`}
      className="pointer-events-none fixed bottom-3 right-3 z-[60] flex items-center gap-2 rounded-full border border-[#1b4a33] bg-[#071a0e]/95 px-3 py-1.5 text-xs text-slate-300 shadow-lg"
    >
      <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" aria-hidden="true" />
      Waking services {answered}/{tracked.length}
    </div>
  )
}

export function useServicesReady(keys) {
  const status = useContext(WarmupContext)
  if (!status) throw new Error('useServicesReady must be used within ServiceWarmupProvider')
  const services = SERVICES.filter((service) => keys.includes(service.key))
  const pending = services.filter((service) => status[service.key] === 'pending').map((service) => service.label)
  const failed = services.filter((service) => status[service.key] === 'timeout').map((service) => service.label)
  return { ready: pending.length === 0 && failed.length === 0, pending, failed }
}
