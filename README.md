# Nigraan AI

Disaster damage assessment & aid-priority platform for NDMA/PDMA — Bano Qabil × Alibaba Cloud AI Hackathon.

## Structure
- `risk-flag/` — pre-storm risk scoring (rainfall + LLM)
- `damage-checker/` — post-storm damage classification (xBD + Alibaba PAI)
- `aid-priority/` — urgency ranking
- `dashboard/` — frontend
- `infra/` — cloud deployment configs

See `API_CONTRACT.md` for interface definitions.