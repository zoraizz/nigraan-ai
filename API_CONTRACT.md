# API Contract — Nigraan AI

## POST /predict-risk
Request:
{ "district": "string", "rainfall_forecast_mm": number }

Response:
{ "district": "string", "risk_level": "low|medium|high", "reason": "string" }

## POST /classify-damage
Request: multipart/form-data, field "image"

Response:
{ "damage_level": "none|partial|destroyed", "confidence": number, "area": "string" }

## GET /aid-priority
Response:
{ "ranked_areas": [ { "area": "string", "urgency_score": number, "damage_summary": {...} } ] }