# Nigraan AI — End-to-End Integration Checklist

Validates the full data flow: **React dashboard (:5173) → three FastAPI backends
(:8000 / :8001 / :8002)**, all running concurrently with CORS.

## 1. Prerequisites

- Node 18+ installed (verified with Node 24)
- `dashboard/node_modules/` present (run `npm install` once inside `dashboard/`)
- Python venvs exist (already the case on this machine)
- `.env` files in place: `risk-flag/.env` (GEMINI_API_KEY),
  `damage-checker/.env` (CHECKPOINT_PATH), `dashboard/.env` (VITE_*_API_URL)
  — all gitignored, values documented in each module's `.env.example`

## 2. Start the four services (four terminals)

```powershell
# Terminal 1 — Risk Flag (:8000)
cd E:\Hackathon\nigraan-ai\risk-flag
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Damage Checker (:8001)  (loads model, needs a few seconds)
cd E:\Hackathon\nigraan-ai\damage-checker
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001

# Terminal 3 — Aid Priority (:8002)
cd E:\Hackathon\nigraan-ai\aid-priority
E:\Hackathon\nigraan-ai\damage-checker\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002

# Terminal 4 — Dashboard (:5173)
cd E:\Hackathon\nigraan-ai\dashboard
npm run dev
```

## 3. Backend smoke checks (before opening the dashboard)

```powershell
curl.exe -s http://127.0.0.1:8000/            # → {"status":"ok","districts_available":[...16...]}
curl.exe -s http://127.0.0.1:8001/health      # → {"status":"ok","model_loaded":true,...}
curl.exe -s http://127.0.0.1:8002/health      # → {"status":"ok","risk_weight":0.4,...}
```

CORS preflight spot-check (expect `200` + `access-control-allow-origin: http://localhost:5173`):

```powershell
curl.exe -s -i -X OPTIONS http://127.0.0.1:8002/rank-priority -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: POST"
```

## 4. Dashboard end-to-end script (open http://localhost:5173)

Keep the browser DevTools console + Network tab open throughout. **There must
be no CORS errors in the console at any step.**

### Step 1 — RiskMap page
1. Click **Risk Map** in the sidebar.
2. A risk card for **Dadu** (default) loads in roughly 3 minutes (observed 172-177 s; the Gemini call dominates).
3. Expected: risk badge (`low`/`medium`/`high`), `Flood` hazard chip,
   "3-day forecast: X mm" row, and a reason sentence.
4. Click another district (e.g. **Tharparkar**) → card refetches (allow another ~3 min); expect
   `Drought` chip and 30-day/90-day rainfall rows.
5. Network tab: one `OPTIONS` (200) then one `POST /predict-risk` (200) per fetch.

### Step 2 — DamageAssessment page
1. Click **Damage Assessment**.
2. Select any post-disaster satellite tile — e.g. an xBD `.png` from
   `E:\Hackathon\nigraan-ai\damage-checker\data\` (any `train`/`val` tile works).
3. Pick an area label (or leave `unknown`), click **Classify damage**.
4. Expected: image preview renders; after ~1–2 s the result card shows
   `none` / `partial` / `destroyed` with a confidence %.
5. Network tab: `OPTIONS` (200) then `POST /classify-damage` (200); request is
   `multipart/form-data`.

### Step 3 — AidPriority page
1. Click **Aid Priority**.
2. Click **Run demo ranking**.
3. Expected table order (hand-computed with default weights 0.4/0.6):

   | Rank | District | Priority | Low-coverage warning |
   |---|---|---|---|
   | 1 | Hunza | 1.0000 | ⚠ yes (1 tile) |
   | 2 | Mansehra | 0.7000 | ⚠ yes (1 tile) |
   | 3 | Rajanpur | 0.6850 | no (100 tiles) |
   | 4 | Tharparkar | 0.4000 | ⚠ yes (1 tile) |
   | 5 | Chitral | 0.3800 | no (25 tiles) |
   | 6 | Dadu | 0.0750 | no (100 tiles) |

4. The scoring panel below must show **live weights** ("live weights from the
   service") — not the static defaults.
5. Network tab: `OPTIONS` (200) then `POST /rank-priority` (200).

### Step 4 — Console
Zero red errors; zero CORS warnings. (React DevTools suggestions are fine.)

## 5. Failure modes and what they mean

| Symptom | Meaning |
|---|---|
| Card shows "Risk Flag request failed — Network error contacting…" | That backend is down (or wrong port). The page stays usable; press Retry after starting it. |
| Console: "blocked by CORS policy" | Backend started without the CORS middleware — you're on an old commit of that service's branch. |
| Damage result unusually fast + header `X-Model-Warning: untrained-weights` | Checkpoint didn't load — check `damage-checker/checkpoints/xbd_real_model_v2.pth` exists. |
| `POST /predict-risk` takes ~3 min | Normal — observed 172-177 s per call (server-side Open-Meteo fetch + Gemini reasoning). Keep waiting; do not restart the backend mid-call. |
| Vite shows "port 5173 is in use" | A previous dev server is still running; stop it or use the alternate port Vite prints (CORS is pinned to 5173, so prefer killing the old one). |

## 6. Direct API checks (optional, no browser)

```powershell
# Risk Flag
curl.exe -s -X POST http://127.0.0.1:8000/predict-risk -H "Content-Type: application/json" -d '{\"district\": \"Dadu\"}'

# Aid Priority (same demo payload as the dashboard)
curl.exe -s -X POST http://127.0.0.1:8002/rank-priority -H "Content-Type: application/json" -d '{\"districts\":[{\"district\":\"Hunza\",\"hazard_type\":\"glof\",\"risk_level\":\"high\",\"overall_damage_level\":\"destroyed\",\"confidence\":0.64},{\"district\":\"Dadu\",\"hazard_type\":\"flood\",\"risk_level\":\"low\",\"damage_breakdown\":{\"none\":80,\"partial\":15,\"destroyed\":5}}]}'
```

Expected priorities from the two-district call: Hunza 1.0, Dadu 0.075.
