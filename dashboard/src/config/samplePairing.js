// District <-> sample-tile pairing for the Aid Priority live pipeline.
//
// Five real districts from config/districts.js (Risk Flag's coverage list),
// spanning a mix of hazard types (flood, drought, glof, landslide), each
// paired with one real sample tile from damage-checker/sample-images/.
// At run time the dashboard fetches each tile via the dev-server
// /sample-images route, classifies it live with POST /classify-damage,
// fetches the district's real risk level with POST /predict-risk, and
// submits both to POST /rank-priority.
//
// There is no live per-district satellite feed, so the district <-> tile
// pairing is ILLUSTRATIVE: the imagery is real and every classification is
// real, but which tile stands in for which district is a demo choice. The
// Pakistan flood tiles are paired with Pakistani monsoon-belt districts; the
// two non-Pakistan xBD tiles (tornado, wildfire) cover the mountain
// districts.
import { DISTRICTS } from './districts.js'

export const SAMPLE_PAIRING = [
  {
    district: 'Dadu',
    tile: 'PAKISTAN-FLOODING_014695_post_disaster.png',
    tileSource: 'EBD Pakistan Flooding (July 2022 floods)',
  },
  {
    district: 'Rajanpur',
    tile: 'PAKISTAN-FLOODING_011306_post_disaster.png',
    tileSource: 'EBD Pakistan Flooding (July 2022 floods)',
  },
  {
    district: 'Tharparkar',
    tile: 'PAKISTAN-FLOODING_018024_post_disaster.png',
    tileSource: 'EBD Pakistan Flooding (July 2022 floods)',
  },
  {
    district: 'Hunza',
    tile: 'joplin-tornado_00000120_post_disaster.png',
    tileSource: 'xBD, Joplin tornado (Missouri, USA)',
  },
  {
    district: 'Mansehra',
    tile: 'santa-rosa-wildfire_00000138_post_disaster.png',
    tileSource: 'xBD, Santa Rosa wildfire (California, USA)',
  },
]

// The district's primary hazard type, from the same districts config the
// rest of the dashboard uses (mirrors Risk Flag's server-side DISTRICTS).
export function hazardTypeFor(districtName) {
  const district = DISTRICTS.find((entry) => entry.name === districtName)
  if (!district || district.hazards.length === 0) {
    throw new Error(`District "${districtName}" not found in districts config`)
  }
  return district.hazards[0]
}
