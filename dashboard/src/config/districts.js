// The 16 districts configured in Risk Flag (server-side DISTRICTS dict in
// risk-flag/main.py) — the authoritative coverage list, mirrored here for
// dropdowns, the risk view, and aid-priority payloads.
// Keep in sync with the Risk Flag module.

export const HAZARD_TYPES = ['flood', 'glof', 'avalanche', 'landslide', 'drought']

export const HAZARD_LABELS = {
  flood: 'Flood',
  glof: 'GLOF',
  avalanche: 'Avalanche',
  landslide: 'Landslide',
  drought: 'Drought',
}

export const DISTRICTS = [
  // ── Flood (Sindh) ──
  { name: 'Dadu', province: 'Sindh', hazards: ['flood'], coords: [26.73033, 67.7769] },
  { name: 'Khairpur', province: 'Sindh', hazards: ['flood'], coords: [27.52948, 68.75915] },
  { name: 'Sukkur', province: 'Sindh', hazards: ['flood'], coords: [27.70323, 68.85889] },
  { name: 'Larkana', province: 'Sindh', hazards: ['flood'], coords: [27.55898, 68.21204] },
  { name: 'Jacobabad', province: 'Sindh', hazards: ['flood'], coords: [28.28187, 68.43761] },
  // ── Flood / hill-torrent (Balochistan & Punjab) ──
  { name: 'Jaffarabad', province: 'Balochistan', hazards: ['flood'], coords: [28.37473, 68.35032] },
  { name: 'D.I. Khan', province: 'Khyber Pakhtunkhwa', hazards: ['flood'], coords: [31.83129, 70.9017] },
  { name: 'D.G. Khan', province: 'Punjab', hazards: ['flood'], coords: [30.04587, 70.64029] },
  { name: 'Rajanpur', province: 'Punjab', hazards: ['flood'], coords: [29.10408, 70.32969] },
  // ── GLOF / Avalanche (Gilgit-Baltistan & KP north) ──
  { name: 'Chitral', province: 'Khyber Pakhtunkhwa', hazards: ['glof', 'avalanche'], coords: [35.8518, 71.78636] },
  { name: 'Hunza', province: 'Gilgit-Baltistan', hazards: ['glof', 'avalanche'], coords: [36.32692, 74.66141] },
  { name: 'Skardu', province: 'Gilgit-Baltistan', hazards: ['glof', 'avalanche'], coords: [35.29787, 75.63372] },
  // ── Landslide (KP north) ──
  { name: 'Mansehra', province: 'Khyber Pakhtunkhwa', hazards: ['landslide'], coords: [34.33023, 73.19679] },
  { name: 'Battagram', province: 'Khyber Pakhtunkhwa', hazards: ['landslide'], coords: [34.67719, 73.02329] },
  // ── Drought (Balochistan & Sindh) ──
  { name: 'Chagai', province: 'Balochistan', hazards: ['drought'], coords: [29.35393, 64.69751] },
  { name: 'Tharparkar', province: 'Sindh', hazards: ['drought'], coords: [24.73701, 69.79707] },
]

export const DISTRICT_NAMES = DISTRICTS.map((district) => district.name)
