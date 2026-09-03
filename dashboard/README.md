# Nigraan AI — Dashboard

React + Vite + Tailwind frontend for the Nigraan disaster response dashboard.

Talks to the three backend services:

| Service | Default base URL | Endpoint used |
|---|---|---|
| Risk Flag | http://127.0.0.1:8000 | POST /predict-risk |
| Damage Checker | http://127.0.0.1:8001 | POST /classify-damage |
| Aid Priority | http://127.0.0.1:8002 | POST /rank-priority |

## Run locally

Requires Node.js 18+ (developed and verified with Node 24).

    cd dashboard
    npm install
    npm run dev

Then open http://localhost:5173.

Backend base URLs are configured via `.env` (copy from `.env.example`;
`.env` is gitignored). The backend services must be running for live data —
every page renders placeholders meanwhile.

## Structure

- `src/api/` — one module per backend service plus the shared fetch wrapper (`client.js`)
- `src/pages/` — the 4 routed pages: Overview, RiskMap, DamageAssessment, AidPriority
- `src/components/` — presentational building blocks (layout/, cards, table, badges)
- `src/hooks/` — data hooks (TODO stubs; intended signatures in each file)
- `src/auth/` — no-op auth scaffolding (AuthProvider / useAuth / ProtectedRoute)
- `src/config/` — district list (mirrors Risk Flag's server-side DISTRICTS) + service endpoints
- `src/styles/` — Tailwind entry CSS

## Notes

- The hooks in `src/hooks/` are intentionally unimplemented TODO stubs — this
  scaffold is meant to be experimented on top of.
- Auth currently passes everyone through (`isAuthenticated: true`); wiring real
  auth later only requires editing the three files in `src/auth/`.
- When the hooks land, the backend services will need CORS enabled for the
  dev origin (http://localhost:5173) — not part of this scaffold.
