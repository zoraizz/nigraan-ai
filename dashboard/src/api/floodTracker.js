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
import { getJson, postJson } from './client.js'

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

// body: { village_ids?: string[], district?: string, as_of?: string }
export async function postAlertDrafts(body) {
  if (FLOOD_USE_FIXTURES) {
    const { drafts } = await loadFixtures()
    const all = Array.isArray(drafts?.drafts) ? drafts.drafts : []
    return { drafts: filterDrafts(all, body) }
  }
  return postJson(ENDPOINTS.floodApi, '/alert-drafts', body ?? {})
}

// source "template" is the fixed label. A model id is shown as "Drafted by <model>".
export function draftTag(draft) {
  if (!draft || draft.source === 'template') return 'Template'
  const model = typeof draft.model === 'string' ? draft.model.trim() : ''
  if (model) return `Drafted by ${model}`
  if (draft.source) return `Drafted by ${draft.source}`
  return 'Template'
}
