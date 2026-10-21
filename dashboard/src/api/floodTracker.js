// River Flood Tracker (port 8003).
// GET /flood-situation?mode=replay&as_of=...
// GET /replay/2022
// POST /alert-drafts
//
// VITE_FLOOD_USE_FIXTURES=true skips the network and reads the hand-made
// JSON copied to src/fixtures/flood/ (from flood-tracker/data/fixtures/).
// Any other value, including unset, calls floodApi. The fixture files are
// examples of the contract shape. They are not gauge readings and not model output.

import { ENDPOINTS } from '../config/endpoints.js'
import { ApiError, getJson, postJson } from './client.js'

export const FLOOD_USE_FIXTURES = String(import.meta.env.VITE_FLOOD_USE_FIXTURES || '').trim() === 'true'

let fixturePromise

function jsonModule(mod) {
  return mod?.default ?? mod
}

function loadFixtures() {
  if (!fixturePromise) {
    fixturePromise = Promise.all([
      import('../fixtures/flood/replay_2022_sample.json'),
      import('../fixtures/flood/situation_2022-08-31.json'),
      import('../fixtures/flood/alert_drafts_sample.json'),
    ]).then(([replay, situation, drafts]) => ({
      replay: jsonModule(replay),
      situation: jsonModule(situation),
      drafts: jsonModule(drafts),
    }))
  }
  return fixturePromise
}

// One replay step, or the standalone 31 Aug situation when asOf is omitted
// or does not match a step. asOf is Asia/Karachi wall time, YYYY-MM-DDTHH:MM.
export async function getFloodSituation(asOf) {
  if (FLOOD_USE_FIXTURES) {
    const { replay, situation } = await loadFixtures()
    const steps = Array.isArray(replay?.steps) ? replay.steps : []
    if (asOf) {
      const match = steps.find((step) => step?.as_of === asOf)
      if (match) return match
    }
    return situation
  }

  const params = new URLSearchParams()
  params.set('mode', 'replay')
  if (asOf) params.set('as_of', asOf)
  return getJson(ENDPOINTS.floodApi, `/flood-situation?${params.toString()}`)
}

export async function getReplay2022() {
  if (FLOOD_USE_FIXTURES) {
    const { replay } = await loadFixtures()
    return replay
  }
  return getJson(ENDPOINTS.floodApi, '/replay/2022')
}

// Today's modelled situation: bias-scaled GloFAS discharge, plus forecast and
// outlook blocks. There is no fixture for it, so fixture mode reports the
// live forecast as unavailable (503) instead of inventing one.
export async function getLiveSituation() {
  if (FLOOD_USE_FIXTURES) {
    throw new ApiError('Live forecast is not available in fixture mode', 503, null)
  }
  return getJson(ENDPOINTS.floodApi, '/flood-situation?mode=live')
}

// body: { barrage, peak_cusecs, peak_time? } -> situation + scenario block.
export async function postWhatIf(body) {
  if (FLOOD_USE_FIXTURES) {
    throw new ApiError('What-if routing is not available in fixture mode', 503, null)
  }
  return postJson(ENDPOINTS.floodApi, '/what-if', body ?? {})
}

function filterDrafts(drafts, body) {
  const ids = Array.isArray(body?.village_ids) ? body.village_ids.filter(Boolean) : []
  const district = typeof body?.district === 'string' ? body.district.trim() : ''
  if (ids.length > 0) {
    const wanted = new Set(ids)
    return drafts.filter((draft) => wanted.has(draft.village_id))
  }
  if (district) return drafts.filter((draft) => draft.district === district)
  return drafts
}

// body: { village_ids?: string[], district?: string, as_of?: string,
//        mode?: 'replay'|'live'|'what_if', scenario?: what-if body }
export async function postAlertDrafts(body) {
  if (FLOOD_USE_FIXTURES) {
    const { drafts } = await loadFixtures()
    const all = Array.isArray(drafts?.drafts) ? drafts.drafts : []
    return { drafts: filterDrafts(all, body) }
  }
  return postJson(ENDPOINTS.floodApi, '/alert-drafts', body ?? {})
}

// The replay step last shown on the Flood Tracker page. Aid Priority reads
// district ETAs for this step; 31 Aug 06:00 when the page was never opened.
const LAST_AS_OF_KEY = 'nigraan.flood.lastAsOf'
export const DEFAULT_FLOOD_AS_OF = '2022-08-31T06:00'

export function rememberFloodAsOf(asOf) {
  if (!asOf) return
  try {
    window.localStorage.setItem(LAST_AS_OF_KEY, asOf)
  } catch {
    // Private mode or storage disabled: Aid Priority falls back to the default.
  }
}

export function lastFloodAsOf() {
  try {
    return window.localStorage.getItem(LAST_AS_OF_KEY) || DEFAULT_FLOOD_AS_OF
  } catch {
    return DEFAULT_FLOOD_AS_OF
  }
}

// villages.json district names that differ from config/districts.js.
const DISTRICT_ALIASES = { 'Dera Ghazi Khan': 'D.G. Khan' }

// { "<dashboard district>": hours } from district_eta_hours at asOf.
// Hours are modelled (earliest at-risk village in the district) and can be
// negative while the arrival window is open; callers clamp for Aid Priority.
export async function getDistrictFloodEtas(asOf) {
  const situation = await getFloodSituation(asOf)
  const etas = {}
  Object.entries(situation?.district_eta_hours ?? {}).forEach(([district, hours]) => {
    const value = Number(hours)
    if (Number.isFinite(value)) etas[DISTRICT_ALIASES[district] ?? district] = value
  })
  return { asOf: situation?.as_of ?? asOf, etas }
}

// The UI shows wave_label, never the internal wave_id. A null label is a rise
// that stayed under Medium Flood or reached it at fewer than 2 barrages.
export function waveName(item) {
  const label = typeof item?.wave_label === 'string' ? item.wave_label.trim() : ''
  return label || 'Minor rise'
}

// source "template" is the fixed label. A model id is shown as "Drafted by <model>".
export function draftTag(draft) {
  if (!draft || draft.source === 'template') return 'Template'
  const model = typeof draft.model === 'string' ? draft.model.trim() : ''
  if (model) return `Drafted by ${model}`
  if (draft.source) return `Drafted by ${draft.source}`
  return 'Template'
}
