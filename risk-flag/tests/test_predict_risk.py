"""
Regression tests for POST /predict-risk.

Usage:
    1. Start the server:  python -m uvicorn main:app --port 8000
    2. Run tests:         python tests/test_predict_risk.py

Requires the `requests` package (already in the risk-flag venv).
"""

import sys
import requests

BASE_URL = "http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Test matrix: (district_name, expected_hazard_types, expected_risk_levels)
# expected_risk_levels is a set of acceptable values (weather-dependent).
# ---------------------------------------------------------------------------

FLOOD_DISTRICTS = [
    ("Dadu", ["flood"]),
    ("Khairpur", ["flood"]),
    ("Sukkur", ["flood"]),
    ("Larkana", ["flood"]),
    ("Jacobabad", ["flood"]),
    ("Jaffarabad", ["flood"]),
    ("D.I. Khan", ["flood"]),
    ("D.G. Khan", ["flood"]),
    ("Rajanpur", ["flood"]),
]

GLOF_AVALANCHE_DISTRICTS = [
    ("Chitral", ["glof", "avalanche"]),
    ("Hunza", ["glof", "avalanche"]),
    ("Skardu", ["glof", "avalanche"]),
]

LANDSLIDE_DISTRICTS = [
    ("Mansehra", ["landslide"]),
    ("Battagram", ["landslide"]),
]

DROUGHT_DISTRICTS = [
    ("Chagai", ["drought"]),
    ("Tharparkar", ["drought"]),
]

ALL_KNOWN = FLOOD_DISTRICTS + GLOF_AVALANCHE_DISTRICTS + LANDSLIDE_DISTRICTS + DROUGHT_DISTRICTS

VALID_RISK_LEVELS = {"low", "medium", "high"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def post_risk(district: str) -> dict:
    r = requests.post(f"{BASE_URL}/predict-risk", json={"district": district}, timeout=15)
    r.raise_for_status()
    return r.json()


def check(condition: bool, label: str, detail: str = "") -> bool:
    if condition:
        print(f"  PASS  {label}")
        return True
    print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
    return False


# ---------------------------------------------------------------------------
# Test groups
# ---------------------------------------------------------------------------
def test_health():
    """GET / returns status ok and lists all 16 districts."""
    r = requests.get(f"{BASE_URL}/", timeout=10)
    r.raise_for_status()
    data = r.json()
    ok = True
    ok &= check(data["status"] == "ok", "status == ok")
    ok &= check(len(data["districts_available"]) == 16,
                f"16 districts listed (got {len(data['districts_available'])})")
    return ok


def test_flood_districts():
    """Flood districts return 3-day rainfall and valid risk level."""
    ok = True
    for district, expected_hazards in FLOOD_DISTRICTS:
        data = post_risk(district)
        ok &= check(
            sorted(data["hazard_types"]) == sorted(expected_hazards),
            f"[{district}] hazard_types == {expected_hazards}",
            f"got {data['hazard_types']}",
        )
        ok &= check(
            data["rainfall_forecast_mm"] is not None,
            f"[{district}] rainfall_forecast_mm is not None",
            f"got {data['rainfall_forecast_mm']}",
        )
        ok &= check(
            data["risk_level"] in VALID_RISK_LEVELS,
            f"[{district}] risk_level is valid",
            f"got {data['risk_level']}",
        )
        # Drought fields should be None for flood-only districts
        ok &= check(
            data["rainfall_30d_mm"] is None and data["rainfall_90d_mm"] is None,
            f"[{district}] drought fields are None",
        )
    return ok


def test_glof_avalanche_districts():
    """GLOF/avalanche districts return no rainfall data, medium risk."""
    ok = True
    for district, expected_hazards in GLOF_AVALANCHE_DISTRICTS:
        data = post_risk(district)
        ok &= check(
            sorted(data["hazard_types"]) == sorted(expected_hazards),
            f"[{district}] hazard_types == {expected_hazards}",
        )
        ok &= check(
            data["rainfall_forecast_mm"] is None,
            f"[{district}] rainfall_forecast_mm is None (non-flood)",
        )
        ok &= check(
            data["risk_level"] == "medium",
            f"[{district}] risk_level == medium (static risk)",
            f"got {data['risk_level']}",
        )
    return ok


def test_landslide_districts():
    """Landslide districts return no rainfall data, medium risk."""
    ok = True
    for district, expected_hazards in LANDSLIDE_DISTRICTS:
        data = post_risk(district)
        ok &= check(
            sorted(data["hazard_types"]) == sorted(expected_hazards),
            f"[{district}] hazard_types == {expected_hazards}",
        )
        ok &= check(
            data["risk_level"] == "medium",
            f"[{district}] risk_level == medium (static risk)",
            f"got {data['risk_level']}",
        )
    return ok


def test_drought_districts():
    """Drought districts return 30-day and 90-day historical rainfall."""
    ok = True
    for district, expected_hazards in DROUGHT_DISTRICTS:
        data = post_risk(district)
        ok &= check(
            sorted(data["hazard_types"]) == sorted(expected_hazards),
            f"[{district}] hazard_types == {expected_hazards}",
        )
        ok &= check(
            data["rainfall_30d_mm"] is not None,
            f"[{district}] rainfall_30d_mm is not None",
            f"got {data['rainfall_30d_mm']}",
        )
        ok &= check(
            data["rainfall_90d_mm"] is not None,
            f"[{district}] rainfall_90d_mm is not None",
            f"got {data['rainfall_90d_mm']}",
        )
        ok &= check(
            data["rainfall_30d_mm"] <= data["rainfall_90d_mm"],
            f"[{district}] 30d <= 90d rainfall",
            f"30d={data['rainfall_30d_mm']}, 90d={data['rainfall_90d_mm']}",
        )
    return ok


def test_unknown_district():
    """Unknown district returns 'unknown' risk level with helpful message."""
    data = post_risk("Nowhere")
    ok = True
    ok &= check(data["risk_level"] == "unknown", "risk_level == unknown")
    ok &= check(data["hazard_types"] == [], "hazard_types is empty")
    ok &= check("Available" in data["reason"], "reason mentions available districts")
    return ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main():
    print(f"Running regression tests against {BASE_URL}\n")

    # Verify server is reachable
    try:
        requests.get(f"{BASE_URL}/", timeout=5)
    except requests.ConnectionError:
        print(f"ERROR: Cannot reach server at {BASE_URL}")
        print("Start it with: python -m uvicorn main:app --port 8000")
        sys.exit(2)

    results = {}
    for name, fn in [
        ("health", test_health),
        ("flood_districts", test_flood_districts),
        ("glof_avalanche_districts", test_glof_avalanche_districts),
        ("landslide_districts", test_landslide_districts),
        ("drought_districts", test_drought_districts),
        ("unknown_district", test_unknown_district),
    ]:
        print(f"\n--- {name} ---")
        results[name] = fn()

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"Groups: {passed}/{total} passed")

    if all(results.values()):
        print("All tests passed!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"FAILED groups: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
