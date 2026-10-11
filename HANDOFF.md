# Nigraan AI — full handoff (2026-10-10 → 2026-10-11)

Single start-to-finish record of planning and shipping through the dashboard UI refresh. UI commit on `origin/dev`: `20542d1` (fast-forward from `0671e19`). Re-check `git log` and Render before assuming live matches this doc. Living bullet status also lives in `STATUS.md`.

---

## 1. What Nigraan is

Disaster-response decision support for NDMA/PDMA (Pakistan). Four services. **`dev` is the integration branch.**

| Service | Port | Role |
|---|---|---|
| risk-flag | 8000 | `POST /predict-risk` `{district}` — Open-Meteo weather + NDMA context → Gemini → optional Grok → rules |
| damage-checker | 8001 | `POST /classify-damage` / `POST /classify-scene` — ResNet-18, OOD guard |
| aid-priority | 8002 | `POST /rank-priority` — `0.4*risk + 0.6*damage` (damage = tile average, never sum) |
| dashboard | 5173 | React 18, Vite, Tailwind v4, HashRouter |

**Live Render:**  
https://nigraan-dashboard.onrender.com · https://nigraan-risk-flag.onrender.com · https://nigraan-damage-checker.onrender.com · https://nigraan-aid-priority.onrender.com  

Manual Deploy from `dev` (auto-deploy unreliable). Cold start 30–60s. Secrets only in Render env.

**Hard limits (say these honestly):** single-image damage (not bi-temporal); tile = worst building; partial class weakest; OOD is a heuristic; Risk Flag is weather + LLM, not a hydro/glacier/avalanche model; town lat/lon grid can understate high-glacier snow; Aid Priority district–tile pairing is illustrative.

---

## 2. Timeline of work (this session arc)

### A. Gemini reliability (not rate limits)

- User had ~$9.20 Gemini credit; Tier 1 usage was tiny (not the failure mode).
- Early “API failing” was often **localhost down** or **PowerShell curl JSON mangling**. Prefer `Invoke-RestMethod`.
- Shipped: `reasoning_source` / `reasoning_error`, default **`gemini-3.8-flash`**, then **Grok** if `XAI_API_KEY` set (`GROK_MODEL` default `grok-4.3`, `https://api.x.ai/v1`), then rule fallback. 15s per attempt.
- Keys: `risk-flag/.env` locally; same vars on Render risk-flag. Never commit keys.

### B. Multi-metric weather + Risk Map

- Branch/work merged as multi-metric Open-Meteo bundle (`weather_bundle.py`).
- Free Open-Meteo only: one forecast call/district; drought + archive 90d; flood + GloFAS discharge.
- Response: `weather_metrics` + `weather_unavailable`; legacy `rainfall_*` kept.
- Snow for Chitral/Hunza/Skardu; Risk Map panel in dashboard.
- Known tip in that era: `189e393` on `origin/dev` (later commits built on this).

### C. Drought availability + messaging (`660c852`)

- Archive dates capped (Asia/Karachi vs UTC); HTTP 400 date recovery once; partial 30d can survive when older 90d days missing.
- Banner/reason: “drought assessment is limited” vs true static-only.
- Live before deploy still showed old null Chagai/Tharparkar history + old banner.

### D. Open-Meteo 429 cooldown (`d010728`)

- Branch `feat/risk-weather-rate-limit` → `origin/dev` at `d010728`.
- On 429: no in-request sleep/retry; process-local cooldown per URL; missing-data flags; no zero-rain poison; in-flight dedupe.
- 57 mocked tests passed. Cooldown dies on process restart.

### E. Backups

| Branch | Tip / note |
|---|---|
| `backup/local-snapshot-20261010` | `016dcba` — early WIP (damage-checker scripts); do not merge whole into `dev` |
| `backup/local-snapshot-20261011` | `f9e0dc6` — before frontend zip; base `d010728`; local unless you push |

Push optional: `git push -u origin backup/local-snapshot-20261011`

### F. Frontend zip → landing page

- Source dump: `tmp/frontend/` (full clone; **only use `tmp/frontend/dashboard/`**).
- Took: Landing, landing.css, HeroMap, Logo, site.js, `public/bg/bg1–5.jpg`, shell routes/theme.
- Kept: RiskMap multi-metric, `riskMetrics.js`, `availabilityNote*`, `riskFlag.js`, `useRiskData.js`.
- Branch `feat/dashboard-landing-from-zip` → merged to `dev`.
- Routes: `#/` landing; console `#/overview`, `#/risk-map`, `#/damage-assessment`, `#/aid-priority`.
- Landing copy fixed: no longer claims GLOF/avalanche/landslide have no live measurements.
- Damage Assessment “Failed to fetch :8001” = **damage-checker not running**, not a landing bug.

### G. Frontend zip → command-center refresh

- Source dump: `tmp/frontend/dashboard/` only. Not committed.
- Branch `feat/dashboard-ui-refresh-from-zip` from `0671e19`, commit `20542d1`, pushed, then fast-forwarded onto `origin/dev`. No force push. Backups were not merged. Render was not deployed.
- Took: `logo.png`, Overview command board, district matrix, charts, hero/stat cards, collapsible sidebar, header menu, image logo, Risk Map list/grid, assessment modal.
- Kept: `riskFlag.js`, `useRiskData.js`, `riskMetrics.js`, `availabilityNote.js` + test (NDMA drought/limited/static wording). Modal still shows `weather_metrics`, snowfall notes, and the availability banner. `reasoning_source` is labeled instead of always saying Gemini.
- Overview rain, saturation, and priority numbers are illustrative. The saturation widget does not call Open-Meteo in the browser.
- Routes unchanged: `#/`, `#/overview`, `#/risk-map`, `#/damage-assessment`, `#/aid-priority`.
- `npm run build` passed. Availability-note tests: 5 passed.

### H. Current git tip (verify with `git log -1`)

UI refresh on `origin/dev`:

`20542d1` — `feat(dashboard): refresh the command overview without replacing live risk`  
(fast-forward from `0671e19`)

A docs commit may sit on top of `20542d1` after this handoff is committed. `git log -1` is the tip. Untracked `data/` (replay dumps) stays out of commits on purpose.

---

## 3. What is on `dev` vs what is live

| Item | On `origin/dev`? | On Render? |
|---|---|---|
| Gemini → Grok → rules + reasoning_* | Yes | Only if risk-flag Manual Deploy after those commits |
| Multi-metric weather + Risk Map panel | Yes | Only if risk-flag **and** dashboard Manual Deploy |
| Drought archive/banner fix (`660c852`) | Yes | Needs Manual Deploy risk-flag + dashboard |
| 429 cooldown (`d010728`) | Yes | Needs Manual Deploy risk-flag |
| Landing page + copy fix (`0671e19`) | Yes | Needs Manual Deploy **dashboard** |
| Command-center UI refresh (`20542d1`) | Yes | Needs Manual Deploy **dashboard** |

If live still looks old: **Manual Deploy is missing**, not “code missing from GitHub.”

---

## 4. Env vars (never commit real values)

**risk-flag (local `.env` + Render):**  
`GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.8-flash`, `XAI_API_KEY`, optional `GROK_MODEL`

**dashboard:**  
`VITE_RISK_API_URL`, `VITE_DAMAGE_API_URL`, `VITE_PRIORITY_API_URL`  
Local defaults often `127.0.0.1:8000/8001/8002`. Live damage: `https://nigraan-damage-checker.onrender.com` (restart Vite after `.env` change).

---

## 5. How to run locally

```powershell
# risk-flag
cd E:\Hackathon\nigraan-ai\risk-flag
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --port 8000

# damage-checker (required for Damage Assessment / scene)
cd E:\Hackathon\nigraan-ai\damage-checker
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --port 8001

# aid-priority
cd E:\Hackathon\nigraan-ai\aid-priority
# use damage-checker venv if that is the project convention
python -m uvicorn main:app --port 8002

# dashboard
cd E:\Hackathon\nigraan-ai\dashboard
npm run dev
# http://localhost:5173/#/
```

Health: risk-flag `GET /` ; damage/aid `GET /health`.

Predict (PowerShell-safe):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict-risk -ContentType 'application/json' -Body '{"district":"Dadu"}'
```

Drought smoke after risk-flag deploy:

```powershell
foreach ($district in @("Chagai", "Tharparkar")) {
  $body = @{ district = $district } | ConvertTo-Json
  Invoke-RestMethod -Uri "https://nigraan-risk-flag.onrender.com/predict-risk" -Method POST -ContentType "application/json" -Body $body -TimeoutSec 120 |
    Select-Object district, rainfall_30d_mm, rainfall_90d_mm, weather_unavailable, rainfall_unavailable, reason
}
```

---

## 6. API contract (risk) — summary

See `API_CONTRACT.md` for full schema. Important fields:

- `weather_metrics` object (null for unknown district)
- `rainfall_*` top-level mirrors
- `rainfall_unavailable`, `weather_unavailable`
- `reasoning_source`: `gemini` | `grok` | `fallback` | `cache`
- `reasoning_error`: `api_error` | `bad_json` | null

---

## 7. Open issues

- Older Render **cached-null** drought history for Chagai/Tharparkar: unexplained; 429 log does not prove account-wide quota.
- Cooldown/dedupe are **process-local** (not shared across workers/restarts).
- Stale weather-cache values are not labeled “stale” to the client.
- `feat/replay` not merged; scene features on `dev` may still need deploy.
- README “Alibaba PAI” claim check still open.
- Next historically: `feat/risk-signals`.
- Do not merge whole `backup/*` into `dev`.

---

## 8. Immediate ops checklist (demo)

1. Render → **risk-flag** → Manual Deploy from `dev` if drought + 429 + multi-metric + LLM chain are not already live.  
2. Render → **dashboard** → Manual Deploy from `dev` (landing + command overview + Risk Map modal + banners). This UI refresh was not deployed.  
3. Confirm Render env on risk-flag: Gemini + XAI keys.  
4. Local Damage Assessment: start `:8001` or point `VITE_DAMAGE_API_URL` at live damage-checker.  
5. Smoke: landing `#/`, Overview `#/overview`, Risk Map Dadu + Chitral (open the assessment), Chagai/Tharparkar history, scene classify with `demo-scene-2x2.png`.

---

## 9. Repo hygiene reminders

- Never commit `.env`, keys, venvs, `node_modules`, multi-GB xBD trees, bulk `data/replay/raw`.  
- Service trees may need `git add -f` (local exclude).  
- Checkpoint `xbd_ebd_v3.pth` stays wrapped dict.  
- `tmp/frontend` is a merge source only — do not commit the dump.

---

*Generated as the session handoff file. Prefer updating `STATUS.md` after each new task. The dashboard UI refresh is `20542d1` on `origin/dev`. Manual Deploy of the dashboard is still required for the live site, and local Damage Assessment still needs damage-checker on port 8001.*
