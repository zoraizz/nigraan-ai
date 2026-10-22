"""Unit tests for the ground-photo intake core. No network and no model.

Run from anywhere:
    damage-checker\\.venv\\Scripts\\python.exe damage-checker\\tests\\test_ground_intake.py
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from PIL import Image  # noqa: E402

from ground_intake.districts import DISTRICTS  # noqa: E402
from ground_intake.geo import (  # noqa: E402
    haversine_km,
    nearest_district,
    read_exif_gps,
    resolve_location,
    strip_exif,
)
from ground_intake.phash import dhash, hamming  # noqa: E402
from ground_intake.rules import district_summary, urgent_reasons  # noqa: E402
from ground_intake.schema import (  # noqa: E402
    DamageLevel,
    GroundReport,
    ImageKind,
    ReportStatus,
    SceneType,
    VlmObservation,
    WaterDepth,
)
from ground_intake.store import JsonReportStore, StoreWritesPaused  # noqa: E402

DADU = next(item for item in DISTRICTS if item["name"] == "Dadu")
SUKKUR = next(item for item in DISTRICTS if item["name"] == "Sukkur")
LARKANA = next(item for item in DISTRICTS if item["name"] == "Larkana")


def _obs(**overrides) -> VlmObservation:
    payload = {
        "image_kind": "ground_disaster",
        "image_confidence": 0.9,
        "scene_type": "flooded_street",
        "damage_level": "none",
        "water": {"present": False, "flowing": False, "depth": "none"},
        "hazards": [],
        "people": {
            "visible": False,
            "count_estimate": None,
            "stranded_or_trapped": False,
            "on_rooftop": False,
            "injured": False,
        },
        "animals": {"livestock_visible": False, "livestock_at_risk": False},
        "needs": [],
        "summary": "Water on the street.",
        "confidence": 0.8,
    }
    for key, value in overrides.items():
        if key in ("water", "people", "animals") and isinstance(value, dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    return VlmObservation.model_validate(payload)


def _report(district: str = "Dadu", **overrides) -> GroundReport:
    location = overrides.pop(
        "location",
        {"district": district, "source": "manual", "village": None, "lat": None, "lon": None},
    )
    observation = _obs(**{
        key: overrides.pop(key)
        for key in list(overrides)
        if key in {
            "image_kind",
            "image_confidence",
            "scene_type",
            "damage_level",
            "water",
            "hazards",
            "people",
            "animals",
            "needs",
            "summary",
            "confidence",
        }
    })
    data = observation.model_dump()
    data["location"] = location
    data.update(overrides)
    return GroundReport.model_validate(data)


def _jpeg_with_gps(lat_dms, lat_ref, lon_dms, lon_ref) -> Image.Image:
    image = Image.new("RGB", (16, 16), (12, 24, 48))
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    # Pillow writes GPS degrees as rationals. The tuples in the test are
    # (numerator, denominator); the reader still accepts rationals on the way back.
    gps[1] = lat_ref
    gps[2] = tuple(part[0] / part[1] for part in lat_dms)
    gps[3] = lon_ref
    gps[4] = tuple(part[0] / part[1] for part in lon_dms)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    buffer.seek(0)
    loaded = Image.open(buffer)
    loaded.load()
    return loaded


class TestUrgentReasons(unittest.TestCase):
    def test_people_trapped(self):
        reasons = urgent_reasons(_obs(people={"stranded_or_trapped": True}))
        self.assertEqual(reasons, ["people_trapped"])

    def test_people_on_rooftop(self):
        reasons = urgent_reasons(_obs(people={"on_rooftop": True}))
        self.assertEqual(reasons, ["people_on_rooftop"])

    def test_people_injured(self):
        reasons = urgent_reasons(_obs(people={"injured": True}))
        self.assertEqual(reasons, ["people_injured"])

    def test_rising_water_near_visible_people(self):
        waist = urgent_reasons(_obs(
            people={"visible": True},
            water={"present": True, "depth": "waist"},
        ))
        flowing = urgent_reasons(_obs(
            people={"visible": True},
            water={"present": True, "flowing": True, "depth": "none"},
        ))
        self.assertEqual(waist, ["rising_water_near_people"])
        self.assertEqual(flowing, ["rising_water_near_people"])

    def test_not_urgent_without_people_or_with_shallow_still_water(self):
        shallow = urgent_reasons(_obs(
            people={"visible": True},
            water={"present": True, "flowing": False, "depth": "ankle"},
        ))
        empty_deep = urgent_reasons(_obs(
            people={"visible": False},
            water={"present": True, "flowing": True, "depth": "above_head"},
        ))
        self.assertEqual(shallow, [])
        self.assertEqual(empty_deep, [])

    def test_reason_order_is_fixed(self):
        reasons = urgent_reasons(_obs(
            people={
                "visible": True,
                "stranded_or_trapped": True,
                "on_rooftop": True,
                "injured": True,
            },
            water={"present": True, "flowing": True, "depth": "chest"},
        ))
        self.assertEqual(reasons, [
            "people_trapped",
            "people_on_rooftop",
            "people_injured",
            "rising_water_near_people",
        ])


class TestDistrictSummary(unittest.TestCase):
    def test_more_photos_is_not_more_damage(self):
        # A: 40 unique, 10 destroyed (25%). B: 3 unique, 2 destroyed (~66%).
        reports = []
        for _ in range(10):
            reports.append(_report("Dadu", damage_level="destroyed"))
        for _ in range(30):
            reports.append(_report("Dadu", damage_level="none"))
        for _ in range(2):
            reports.append(_report("Sukkur", damage_level="destroyed"))
        reports.append(_report("Sukkur", damage_level="none"))

        summary = district_summary(reports)["districts"]
        dadu = summary["Dadu"]
        sukkur = summary["Sukkur"]

        self.assertEqual(dadu["report_count"], 40)
        self.assertEqual(sukkur["report_count"], 3)
        self.assertAlmostEqual(dadu["ground_score"], 0.25)
        self.assertAlmostEqual(sukkur["ground_score"], 2 / 3)
        self.assertAlmostEqual(dadu["share_destroyed"], 0.25)
        self.assertAlmostEqual(sukkur["share_destroyed"], 2 / 3)
        self.assertGreater(sukkur["ground_score"], dadu["ground_score"])

    def test_duplicates_and_rejected_are_excluded_from_the_score(self):
        canonical = _report("Rajanpur", damage_level="partial", scene_type="flooded_street")
        duplicate = _report(
            "Rajanpur",
            damage_level="destroyed",
            scene_type="collapsed_house",
            duplicate_of=canonical.id,
            urgent=True,
            status="verified",
        )
        rejected = _report(
            "Rajanpur",
            damage_level="destroyed",
            status="rejected",
            urgent=True,
        )
        verified = _report(
            "Rajanpur",
            damage_level="destroyed",
            status="verified",
            urgent=True,
            scene_type="debris",
        )

        row = district_summary([canonical, duplicate, rejected, verified])["districts"]["Rajanpur"]

        self.assertEqual(row["report_count"], 2)
        self.assertEqual(row["photo_count"], 3)
        self.assertEqual(row["verified_count"], 1)
        self.assertEqual(row["severity_mix"], {"none": 0, "partial": 1, "destroyed": 1})
        self.assertAlmostEqual(row["ground_score"], (0.5 + 1.0) / 2)
        self.assertAlmostEqual(row["share_damaged"], 1.0)
        self.assertEqual(row["urgent_open"], 1)
        self.assertEqual(row["top_scene_types"], [
            {"scene_type": "debris", "count": 1},
            {"scene_type": "flooded_street", "count": 1},
        ])

    def test_low_sample_warning(self):
        two = district_summary([
            _report("Larkana", damage_level="partial"),
            _report("Larkana", damage_level="none"),
        ])["districts"]["Larkana"]
        three = district_summary([
            _report("Larkana", damage_level="none"),
            _report("Larkana", damage_level="none"),
            _report("Larkana", damage_level="none"),
        ])["districts"]["Larkana"]
        canonical = _report("Jacobabad", damage_level="destroyed")
        duplicates = [
            _report("Jacobabad", damage_level="destroyed", duplicate_of=canonical.id)
            for _ in range(5)
        ]
        thin = district_summary([canonical, *duplicates])["districts"]["Jacobabad"]

        self.assertEqual(two["report_count"], 2)
        self.assertEqual(two["low_sample_warning"], "low sample — based on 2 reports")
        self.assertEqual(three["report_count"], 3)
        self.assertIsNone(three["low_sample_warning"])
        self.assertEqual(thin["report_count"], 1)
        self.assertEqual(thin["photo_count"], 6)
        self.assertEqual(thin["low_sample_warning"], "low sample — based on 1 report")

    def test_corrected_values_are_what_the_score_reads(self):
        original = _obs(damage_level="none", scene_type="flooded_street")
        corrected = _report(
            "Sukkur",
            damage_level="destroyed",
            scene_type="landslide",
            status="corrected",
            review={"history": [], "ai_original": original.model_dump()},
        )

        row = district_summary([corrected])["districts"]["Sukkur"]

        self.assertEqual(row["severity_mix"]["destroyed"], 1)
        self.assertEqual(row["severity_mix"]["none"], 0)
        self.assertEqual(row["verified_count"], 1)
        self.assertEqual(row["top_scene_types"], [{"scene_type": "landslide", "count": 1}])
        self.assertAlmostEqual(row["ground_score"], 1.0)

    def test_top_scene_types_keep_three(self):
        reports = []
        for _ in range(5):
            reports.append(_report("Dadu", scene_type="flooded_street"))
        for _ in range(3):
            reports.append(_report("Dadu", scene_type="debris"))
        for _ in range(2):
            reports.append(_report("Dadu", scene_type="landslide"))
        reports.append(_report("Dadu", scene_type="relief_camp"))

        top = district_summary(reports)["districts"]["Dadu"]["top_scene_types"]
        self.assertEqual(top, [
            {"scene_type": "flooded_street", "count": 5},
            {"scene_type": "debris", "count": 3},
            {"scene_type": "landslide", "count": 2},
        ])


class TestEnumCoercion(unittest.TestCase):
    def test_unknown_strings_become_safe_values(self):
        obs = _obs(
            image_kind="painting",
            scene_type="spaceship",
            damage_level="catastrophic",
            water={"present": True, "flowing": False, "depth": "eyebrows"},
            hazards=["fire", "meteor"],
            needs=["rescue", "helicopter"],
        )
        self.assertEqual(obs.image_kind, ImageKind.irrelevant)
        self.assertEqual(obs.scene_type, SceneType.other_disaster)
        self.assertEqual(obs.damage_level, DamageLevel.none)
        self.assertEqual(obs.water.depth, WaterDepth.none)
        self.assertEqual([item.value for item in obs.hazards], ["fire"])
        self.assertEqual([item.value for item in obs.needs], ["rescue"])

    def test_known_values_round_trip(self):
        obs = _obs(
            scene_type="Collapsed_House",
            damage_level="Destroyed",
            water={"depth": "Above_Head", "present": True, "flowing": True},
        )
        self.assertEqual(obs.scene_type, SceneType.collapsed_house)
        self.assertEqual(obs.damage_level, DamageLevel.destroyed)
        self.assertEqual(obs.water.depth, WaterDepth.above_head)


class TestDHash(unittest.TestCase):
    def _ramp(self, reverse: bool = False) -> Image.Image:
        image = Image.new("L", (9, 8))
        pixels = []
        for _row in range(8):
            row = [index * 20 for index in range(9)]
            if reverse:
                row = list(reversed(row))
            pixels.extend(row)
        image.putdata(pixels)
        return image

    def test_identical_near_and_different(self):
        image = self._ramp()
        same = dhash(image)
        copy = dhash(image.copy())
        self.assertEqual(len(same), 16)
        self.assertEqual(same, copy)
        self.assertEqual(hamming(same, copy), 0)

        nudged = image.copy()
        nudged.putpixel((0, 0), 255)
        distance = hamming(same, dhash(nudged))
        self.assertGreater(distance, 0)
        self.assertLessEqual(distance, 8)

        far = hamming(same, dhash(self._ramp(reverse=True)))
        self.assertGreaterEqual(far, 32)


class TestGeo(unittest.TestCase):
    def test_district_table_matches_the_dashboard_list(self):
        self.assertEqual(len(DISTRICTS), 16)
        self.assertEqual(DISTRICTS[0]["name"], "Dadu")
        self.assertEqual(DISTRICTS[0]["lat"], 26.73033)
        self.assertEqual(DISTRICTS[0]["lon"], 67.7769)
        self.assertEqual(DISTRICTS[-1]["name"], "Tharparkar")

    def test_exif_gps_parsing(self):
        plain = Image.new("RGB", (8, 8), (1, 2, 3))
        self.assertIsNone(read_exif_gps(plain))

        north_east = _jpeg_with_gps(
            ((27, 1), (30, 1), (0, 1)),
            "N",
            ((68, 1), (15, 1), (0, 1)),
            "E",
        )
        lat, lon = read_exif_gps(north_east)
        self.assertAlmostEqual(lat, 27.5)
        self.assertAlmostEqual(lon, 68.25)

        south_west = _jpeg_with_gps(
            ((10, 1), (30, 1), (0, 1)),
            "S",
            ((5, 1), (0, 1), (0, 1)),
            b"W",
        )
        lat, lon = read_exif_gps(south_west)
        self.assertAlmostEqual(lat, -10.5)
        self.assertAlmostEqual(lon, -5.0)

        stripped = strip_exif(north_east)
        self.assertIsNone(read_exif_gps(stripped))
        buffer = io.BytesIO()
        stripped.save(buffer, format="JPEG")
        buffer.seek(0)
        reloaded = Image.open(buffer)
        reloaded.load()
        self.assertIsNone(read_exif_gps(reloaded))

    def test_nearest_district_within_and_beyond(self):
        self.assertEqual(
            nearest_district(float(DADU["lat"]), float(DADU["lon"]), max_km=0),
            "Dadu",
        )
        lat = float(DADU["lat"]) + 0.05
        lon = float(DADU["lon"])
        distance = haversine_km(lat, lon, float(DADU["lat"]), float(DADU["lon"]))
        self.assertGreater(distance, 1)
        self.assertLess(distance, 20)
        self.assertEqual(nearest_district(lat, lon, max_km=20), "Dadu")
        self.assertIsNone(nearest_district(lat, lon, max_km=1))

    def test_resolve_location_priority(self):
        exif_over_device = resolve_location(
            (float(SUKKUR["lat"]), float(SUKKUR["lon"])),
            float(DADU["lat"]),
            float(DADU["lon"]),
            "Dadu",
            "Ali Wahan",
            30,
        )
        self.assertEqual(exif_over_device["source"], "exif")
        self.assertEqual(exif_over_device["district"], "Sukkur")
        self.assertEqual(exif_over_device["lat"], float(SUKKUR["lat"]))
        self.assertEqual(exif_over_device["village"], "Ali Wahan")

        device = resolve_location(
            None,
            float(LARKANA["lat"]),
            float(LARKANA["lon"]),
            "Dadu",
            "Bakrani",
            30,
        )
        self.assertEqual(device["source"], "device")
        self.assertEqual(device["district"], "Larkana")

        device_far = resolve_location(None, 0.0, 0.0, "Dadu", None, 50)
        self.assertEqual(device_far["source"], "device")
        self.assertEqual(device_far["district"], "Dadu")
        self.assertEqual(device_far["lat"], 0.0)
        self.assertIsNone(device_far["village"])

        exif_far = resolve_location(
            (0.0, 0.0),
            float(DADU["lat"]),
            float(DADU["lon"]),
            "Khairpur",
            "  Kot  ",
            50,
        )
        self.assertEqual(exif_far["source"], "exif")
        self.assertEqual(exif_far["lat"], 0.0)
        self.assertEqual(exif_far["district"], "Khairpur")
        self.assertEqual(exif_far["village"], "Kot")

        manual = resolve_location(None, None, None, "Khairpur", "Kot", 50)
        self.assertEqual(manual["source"], "manual")
        self.assertIsNone(manual["lat"])
        self.assertIsNone(manual["lon"])
        self.assertEqual(manual["district"], "Khairpur")

        unknown = resolve_location(None, None, None, "  ", None, 50)
        self.assertEqual(unknown["source"], "unknown")
        self.assertIsNone(unknown["district"])
        self.assertIsNone(unknown["lat"])


class VisionLayerTests(unittest.TestCase):
    def setUp(self):
        from ground_intake import vlm
        self.vlm = vlm
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(vlm.set_providers_for_tests, None)

    def fake(self, name, *results, configured=True):
        provider = Mock()
        provider.name = name
        provider.model = "fake-model"
        provider.configured = configured
        provider.describe.side_effect = results
        return provider

    def test_parse_plain_fenced_and_first_object(self):
        raw = _obs(summary='Damage near a wall marked "}".').model_dump_json()
        for text in (raw, f"```json\n{raw}\n```", f"Result: {raw} {{}} trailing"):
            with self.subTest(text=text):
                self.assertEqual(self.vlm.parse_observation(text), _obs(summary='Damage near a wall marked "}".'))

    def test_parse_unknown_enums_and_invalid_output(self):
        data = _obs().model_dump(mode="json")
        data.update(image_kind="unknown", scene_type="unknown", damage_level="unknown",
                    hazards=["unknown"], needs=["unknown"])
        data["water"]["depth"] = "unknown"
        result = self.vlm.parse_observation(json.dumps(data))
        self.assertEqual(result.image_kind, ImageKind.irrelevant)
        self.assertEqual(result.scene_type, SceneType.other_disaster)
        self.assertEqual(result.damage_level, DamageLevel.none)
        self.assertEqual(result.water.depth, WaterDepth.none)
        self.assertEqual(result.hazards, [])
        self.assertEqual(result.needs, [])
        for text in ("bad", "{}", '{"broken":', None):
            with self.assertRaises(self.vlm.InvalidObservation):
                self.vlm.parse_observation(text)

    def test_prepare_image(self):
        original = Image.new("RGBA", (2400, 1200), "red")
        with Image.open(io.BytesIO(self.vlm.prepare_image(original))) as result:
            self.assertEqual(result.mode, "RGB")
            self.assertEqual(result.size, (1024, 512))
            self.assertEqual(result.format, "JPEG")
        self.assertEqual(original.size, (2400, 1200))
        with Image.open(io.BytesIO(self.vlm.prepare_image(Image.new("L", (20, 10))))) as result:
            self.assertEqual(result.size, (20, 10))

    def test_chain_skips_and_falls_through(self):
        skip = self.fake("skip", configured=False)
        fail = self.fake("fail", RuntimeError("transport failure"))
        bad = self.fake("bad", self.vlm.InvalidObservation(), self.vlm.InvalidObservation())
        good = self.fake("good", _obs())
        self.vlm.set_providers_for_tests([skip, fail, bad, good])
        self.assertEqual(self.vlm.describe_with_chain(b"jpeg"), (_obs(), "good", "fake-model"))
        skip.describe.assert_not_called()
        self.assertEqual(fail.describe.call_count, 1)
        self.assertEqual(bad.describe.call_count, 2)
        good.describe.assert_called_once_with(b"jpeg")

    def test_retry_can_succeed_and_does_not_override_irrelevant(self):
        result = _obs(image_kind="irrelevant")
        first = self.fake("first", self.vlm.InvalidObservation(), result)
        later = self.fake("later", _obs())
        self.vlm.set_providers_for_tests([first, later])
        self.assertEqual(self.vlm.describe_with_chain(b"jpeg")[0], result)
        self.assertEqual(first.describe.call_count, 2)
        later.describe.assert_not_called()

    def test_unavailable(self):
        for providers in ([], [self.fake("skip", configured=False)],
                          [self.fake("bad", self.vlm.InvalidObservation(), self.vlm.InvalidObservation())]):
            self.vlm.set_providers_for_tests(providers)
            with self.assertRaises(self.vlm.VlmUnavailable):
                self.vlm.describe_with_chain(b"jpeg")

    def test_environment_order_and_no_keys(self):
        with patch.object(self.vlm, "_providers", {}):
            self.assertEqual([p.name for p in self.vlm._configured_chain()], ["gemini"])
            with self.assertRaises(self.vlm.VlmUnavailable):
                self.vlm.describe_with_chain(b"jpeg")
            os.environ["GROUND_VLM_PROVIDERS"] = "qwen,unknown,gemini,qwen"
            self.assertEqual([p.name for p in self.vlm._configured_chain()], ["qwen", "gemini"])

    def test_gemini_mocked_client_is_lazy_and_reused(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only", "GROUND_VLM_TIMEOUT_SECONDS": "2.5"}), \
                patch("google.genai.Client") as client:
            provider = self.vlm.GeminiProvider()
            client.assert_not_called()
            client.return_value.models.generate_content.return_value.text = _obs().model_dump_json()
            self.assertEqual(provider.describe(b"jpeg"), _obs())
            provider.describe(b"jpeg")
            client.assert_called_once()
            self.assertEqual(client.call_args.kwargs["http_options"].timeout, 2500)
            args = client.return_value.models.generate_content.call_args.kwargs
            self.assertEqual(args["model"], "gemini-3.8-flash")
            self.assertEqual(args["contents"][0].inline_data.data, b"jpeg")
            self.assertEqual(args["contents"][0].inline_data.mime_type, "image/jpeg")
            self.assertEqual(args["contents"][1], self.vlm.PROMPT)
            self.assertEqual(args["config"].response_mime_type, "application/json")
            self.assertIs(args["config"].response_schema, VlmObservation)
            self.assertEqual(args["config"].temperature, 0.2)

    def test_qwen_request_and_bad_json_retry(self):
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-only",
                                   "DASHSCOPE_BASE_URL": "https://example.test/v1/",
                                   "DASHSCOPE_VL_MODEL": "test-model"}), \
                patch.object(self.vlm.requests, "post") as post:
            provider = self.vlm.QwenDashScopeProvider()
            post.return_value.json.return_value = {"choices": [{"message": {"content": _obs().model_dump_json()}}]}
            self.assertEqual(provider.describe(b"jpeg"), _obs())
            self.assertEqual(post.call_args.args[0], "https://example.test/v1/chat/completions")
            args = post.call_args.kwargs
            self.assertEqual(args["headers"]["Authorization"], "Bearer test-only")
            self.assertEqual(args["timeout"], 20)
            self.assertEqual(args["json"]["model"], "test-model")
            content = args["json"]["messages"][0]["content"]
            self.assertEqual(content[0], {"type": "text", "text": self.vlm.PROMPT})
            self.assertEqual(content[1]["image_url"]["url"], "data:image/jpeg;base64,anBlZw==")
            post.return_value.raise_for_status.assert_called_once()
            post.reset_mock()
            post.return_value.json.return_value = {"choices": [{"message": {"content": "bad JSON"}}]}
            self.vlm.set_providers_for_tests([provider, self.fake("fallback", _obs())])
            self.assertEqual(self.vlm.describe_with_chain(b"jpeg")[1], "fallback")
            self.assertEqual(post.call_count, 2)

    def test_timeout_safe_defaults(self):
        for value in ("", "invalid", "0", "-1", "nan", "inf"):
            os.environ["GROUND_VLM_TIMEOUT_SECONDS"] = value
            self.assertEqual(self.vlm._timeout_seconds(), 20)


# ---- POST /intake ----

SAMPLE_DIR = SERVICE_ROOT / "sample-images"
_FORCED_OOD = {
    "cosine": 0.5,
    "mahalanobis": 30.0,
    "cosine_threshold": 0.3,
    "mahalanobis_threshold": 20.0,
    "photo_cosine": 0.6,
    "photo_mahalanobis": 40.0,
    "photo_score": 3.1,
    "photo_score_threshold": 2.0,
    "signals": ["photo_content"],
    "is_out_of_domain": True,
}


def _forced_ood_classify(_pil):
    return {"damage_level": "partial", "confidence": 0.41, "ood": dict(_FORCED_OOD)}


def _photo_bytes(fmt: str = "PNG", seed: int = 0) -> bytes:
    image = Image.new("RGB", (64, 48))
    image.putdata([((x * 4 + seed) % 256, (y * 5) % 256, (x * y + seed) % 256)
                   for y in range(48) for x in range(64)])
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _call_intake(intake, data: bytes, **query):
    import asyncio

    from fastapi import UploadFile

    params = {"district": None, "village": None, "lat": None, "lon": None,
              "reporter_role": None}
    params.update(query)
    response = asyncio.run(intake(
        image=UploadFile(file=io.BytesIO(data), filename="upload.png"), **params))
    return response.status_code, json.loads(response.body), response.headers


def _intake_endpoint(router):
    return next(route.endpoint for route in router.routes if route.path == "/intake")


class _IntakeBase(unittest.TestCase):
    def setUp(self):
        from ground_intake import router as router_module
        from ground_intake import vlm
        self.router_module = router_module
        self.vlm = vlm
        self.store = router_module.set_store_for_tests()
        self.addCleanup(router_module.set_store_for_tests)
        self.addCleanup(vlm.set_providers_for_tests, None)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ("GROUND_MAX_UPLOAD_BYTES", "GROUND_MIN_CONFIDENCE",
                     "GROUND_DISTRICT_MAX_KM", "GROUND_DUPLICATE_MAX_HAMMING"):
            os.environ.pop(name, None)

    def provider(self, *results):
        fake = Mock()
        fake.name = "fake"
        fake.model = "fake-vl"
        fake.configured = True
        fake.describe.side_effect = results
        self.vlm.set_providers_for_tests([fake])
        return fake


class TestIntakeRouting(_IntakeBase):
    """Stubbed classify_pil and a fake provider. No torch model needed."""

    def setUp(self):
        super().setUp()
        self.intake = _intake_endpoint(
            self.router_module.build_router(_forced_ood_classify))

    def test_forced_ood_ground_disaster_becomes_an_urgent_report(self):
        fake = self.provider(_obs(
            image_confidence=0.9,
            damage_level="destroyed",
            water={"present": True, "flowing": True, "depth": "waist"},
            people={"visible": True, "count_estimate": 3, "on_rooftop": True},
        ))
        status, body, headers = _call_intake(
            self.intake, _photo_bytes(), district=" Dadu ", village="Johi",
            reporter_role="rescue_team")
        self.assertEqual(status, 200)
        self.assertEqual(body["route"], "ground")
        report = body["report"]
        self.assertTrue(report["urgent"])
        self.assertEqual(report["urgent_reasons"],
                         ["people_on_rooftop", "rising_water_near_people"])
        self.assertEqual(report["status"], "unverified")
        self.assertEqual(report["damage_level"], "destroyed")
        self.assertEqual(report["location"]["district"], "Dadu")
        self.assertEqual(report["location"]["village"], "Johi")
        self.assertEqual(report["location"]["source"], "manual")
        self.assertEqual(report["reporter_role"], "rescue_team")
        self.assertEqual((report["vlm_source"], report["vlm_model"]), ("fake", "fake-vl"))
        self.assertEqual(len(report["phash"]), 16)
        self.assertIsNone(report["duplicate_of"])
        self.assertEqual(report["review"]["ai_original"]["damage_level"], "destroyed")
        self.assertNotIn("x-model-warning", headers)
        # The model got an EXIF-free JPEG, and that JPEG is what was stored.
        jpeg = fake.describe.call_args.args[0]
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        stored = self.store.photo_path(report["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored.read_bytes(), jpeg)
        self.assertEqual(self.store.get(report["id"]).id, report["id"])

    def test_not_urgent_and_unknown_role_defaults_to_citizen(self):
        self.provider(_obs())
        _, body, _ = _call_intake(self.intake, _photo_bytes(), reporter_role="mayor")
        self.assertFalse(body["report"]["urgent"])
        self.assertEqual(body["report"]["urgent_reasons"], [])
        self.assertEqual(body["report"]["reporter_role"], "citizen")
        self.assertEqual(body["report"]["location"]["source"], "unknown")

    def test_duplicates_point_at_the_group_first_report(self):
        self.provider(_obs(), _obs(), _obs(), _obs())
        _, first, _ = _call_intake(self.intake, _photo_bytes(), district="Dadu")
        _, second, _ = _call_intake(self.intake, _photo_bytes("JPEG"), district="Dadu")
        _, third, _ = _call_intake(self.intake, _photo_bytes(), district="Dadu")
        _, elsewhere, _ = _call_intake(self.intake, _photo_bytes(), district="Sukkur")
        first_id = first["report"]["id"]
        self.assertIsNone(first["report"]["duplicate_of"])
        self.assertEqual(second["report"]["duplicate_of"], first_id)
        self.assertEqual(third["report"]["duplicate_of"], first_id)
        self.assertIsNone(elsewhere["report"]["duplicate_of"])

    def test_duplicates_within_one_km_across_districts(self):
        self.provider(_obs(), _obs())
        _, first, _ = _call_intake(self.intake, _photo_bytes(), lat=24.0, lon=62.0)
        _, second, _ = _call_intake(self.intake, _photo_bytes(), lat=24.005, lon=62.0)
        self.assertIsNone(first["report"]["location"]["district"])
        self.assertEqual(second["report"]["location"]["source"], "device")
        self.assertEqual(second["report"]["duplicate_of"], first["report"]["id"])

    def test_exif_gps_from_the_original_upload_picks_the_district(self):
        self.provider(_obs())
        image = _jpeg_with_gps(((26, 1), (43, 1), (4919, 100)), "N",
                               ((67, 1), (46, 1), (3684, 100)), "E")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=image.getexif().tobytes())
        _, body, _ = _call_intake(self.intake, buffer.getvalue(), district="Sukkur")
        location = body["report"]["location"]
        self.assertEqual(location["source"], "exif")
        self.assertEqual(location["district"], "Dadu")
        self.assertAlmostEqual(location["lat"], DADU["lat"], places=3)
        with Image.open(self.store.photo_path(body["report"]["id"])) as saved:
            saved.load()
            self.assertEqual(saved.format, "JPEG")
            self.assertLessEqual(max(saved.size), 1024)
            self.assertFalse(saved.getexif().get_ifd(0x8825))

    def test_rejections_keep_the_classify_damage_message(self):
        cases = [
            ("vlm_irrelevant", [_obs(image_kind="irrelevant", image_confidence=0.95)]),
            ("vlm_aerial", [_obs(image_kind="aerial_or_satellite", image_confidence=0.95)]),
            ("vlm_low_confidence", [_obs(image_confidence=0.4)]),
            ("vlm_unavailable", None),
            ("vlm_unavailable", [self.vlm.InvalidObservation(), self.vlm.InvalidObservation()]),
            ("vlm_unavailable", [TimeoutError("slow")]),
        ]
        expected_ood = {key: value for key, value in _FORCED_OOD.items()
                        if key != "is_out_of_domain"}
        for reason, results in cases:
            with self.subTest(reason=reason, results=results):
                if results is None:
                    self.vlm.set_providers_for_tests([])
                else:
                    self.provider(*results)
                status, body, _ = _call_intake(self.intake, _photo_bytes(), district="Dadu")
                self.assertEqual(status, 200)
                self.assertEqual(body, {
                    "route": "irrelevant",
                    "message": self.router_module.OOD_MESSAGE,
                    "reason": reason,
                    "ood": expected_ood,
                })
        self.assertEqual(self.store.list(), [])

    def test_min_confidence_env(self):
        os.environ["GROUND_MIN_CONFIDENCE"] = "0.3"
        self.provider(_obs(image_confidence=0.4))
        self.assertEqual(_call_intake(self.intake, _photo_bytes())[1]["route"], "ground")

    def test_oversize_is_413_and_bad_bytes_is_400(self):
        os.environ["GROUND_MAX_UPLOAD_BYTES"] = "100"
        fake = self.provider(_obs())
        status, body, _ = _call_intake(self.intake, _photo_bytes())
        self.assertEqual((status, body["code"]), (413, "image_too_large"))
        os.environ.pop("GROUND_MAX_UPLOAD_BYTES")
        status, body, _ = _call_intake(self.intake, b"not an image")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": self.router_module.INVALID_IMAGE_MESSAGE,
                                "code": "invalid_image"})
        fake.describe.assert_not_called()

    def test_untrained_weights_header(self):
        self.provider(_obs())
        intake = _intake_endpoint(self.router_module.build_router(
            _forced_ood_classify, model_loaded=lambda: False))
        _, _, headers = _call_intake(intake, _photo_bytes())
        self.assertEqual(headers["x-model-warning"], "untrained-weights")

    def test_health_fields_hold_names_only(self):
        self.vlm.set_providers_for_tests([])
        self.assertEqual(self.router_module.ground_health(), {
            "ground_vlm_providers": [],
            "ground_vlm_configured": False,
            "ground_report_count": 0,
        })


class TestIntakeMatchesClassifyDamage(_IntakeBase):
    """Real model: the satellite route must equal /classify-damage."""

    @classmethod
    def setUpClass(cls):
        import asyncio

        cls._cwd = os.getcwd()
        os.chdir(SERVICE_ROOT)
        import main
        cls.main = main
        asyncio.run(main.startup())

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def _classify_damage(self, data: bytes, area: str):
        import asyncio

        from fastapi import UploadFile

        response = asyncio.run(self.main.classify_damage(
            image=UploadFile(file=io.BytesIO(data), filename="upload.png"), area=area))
        return response.status_code, json.loads(response.body), response.headers

    def test_sample_routes_to_satellite_with_identical_fields(self):
        intake = _intake_endpoint(self.router_module.build_router(
            self.main._classify_pil, model_loaded=lambda: self.main._model_loaded))
        fake = self.provider(_obs())
        for name in ("joplin-tornado_00000120_post_disaster.png",
                     "PAKISTAN-FLOODING_014695_post_disaster.png"):
            with self.subTest(sample=name):
                data = (SAMPLE_DIR / name).read_bytes()
                status, body, headers = _call_intake(intake, data, district="Dadu")
                expected_status, expected, expected_headers = self._classify_damage(data, "Dadu")
                self.assertEqual(status, expected_status)
                self.assertEqual(body["route"], "satellite")
                self.assertEqual(body["satellite"], expected)
                self.assertEqual(json.dumps(body["satellite"]), json.dumps(expected))
                self.assertEqual(headers.get("x-model-warning"),
                                 expected_headers.get("x-model-warning"))
        # No area given: /classify-damage's default is "unknown".
        data = (SAMPLE_DIR / "joplin-tornado_00000120_post_disaster.png").read_bytes()
        self.assertEqual(_call_intake(intake, data)[1]["satellite"],
                         self._classify_damage(data, "unknown")[1])
        fake.describe.assert_not_called()

    def test_rejection_message_and_ood_match_classify_damage(self):
        with patch.object(self.main, "_classify_pil", _forced_ood_classify):
            _, expected, _ = self._classify_damage(_photo_bytes(), "Dadu")
        self.assertEqual(expected["message"], self.router_module.OOD_MESSAGE)
        self.vlm.set_providers_for_tests([])
        intake = _intake_endpoint(self.router_module.build_router(_forced_ood_classify))
        _, body, _ = _call_intake(intake, _photo_bytes(), district="Dadu")
        self.assertEqual(body["message"], expected["message"])
        self.assertEqual(body["ood"], expected["ood"])
        _, bad, _ = self._classify_damage(b"not an image", "Dadu")
        self.assertEqual(bad["error"], self.router_module.INVALID_IMAGE_MESSAGE)

    def test_app_mounts_intake_and_health_reports_ground_fields(self):
        import asyncio

        paths = self.main.app.openapi()["paths"]
        for path in (
            "/intake",
            "/ground-reports",
            "/ground-reports/{report_id}",
            "/ground-reports/{report_id}/photo",
            "/ground-reports/{report_id}/review",
            "/ground-summary",
        ):
            self.assertIn(path, paths)
        self.assertIn("patch", paths["/ground-reports/{report_id}/review"])
        self.vlm.set_providers_for_tests([])
        health = asyncio.run(self.main.health())
        self.assertEqual(health["ground_vlm_providers"], [])
        self.assertFalse(health["ground_vlm_configured"])
        self.assertEqual(health["ground_report_count"], 0)


# ---- persistence and officer review ----

_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _tiny_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
            return route.endpoint
    found = [getattr(route, "path", None) for route in router.routes]
    raise AssertionError(f"{method} {path} is not routed; have {found}")


def _json(endpoint, **kwargs):
    import asyncio

    response = asyncio.run(endpoint(**kwargs))
    return response.status_code, json.loads(response.body)


class _StoreBase(unittest.TestCase):
    """GROUND_REPORTS_DIR points at a temp directory for the whole test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._env = patch.dict(os.environ, {"GROUND_REPORTS_DIR": self.tmp.name})
        self._env.start()
        self.addCleanup(self._env.stop)
        from ground_intake import router as router_module
        self.router_module = router_module
        # Constructed with no path so it has to read GROUND_REPORTS_DIR.
        self.store = router_module.set_store_for_tests(JsonReportStore())
        self.addCleanup(router_module.set_store_for_tests)

    def _save(self, district: str = "Dadu", **overrides) -> GroundReport:
        report = _report(district, **overrides)
        self.store.add(report, _tiny_jpeg())
        return report


class TestReportStore(_StoreBase):
    def test_add_reload_and_update_round_trip(self):
        jpeg = _tiny_jpeg()
        report = _report("Dadu", summary="گھر گر گیا۔")
        self.store.add(report, jpeg)

        again = JsonReportStore()
        self.assertEqual(again.root, Path(self.tmp.name).resolve())
        self.assertEqual(again.count(), 1)
        self.assertEqual(again.get(report.id).model_dump(), report.model_dump())
        photo = again.photo_path(report.id)
        self.assertIsNotNone(photo)
        self.assertEqual(photo.name, f"{report.id}.jpg")
        self.assertEqual(photo.read_bytes(), jpeg)
        saved = json.loads((again.root / "reports.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["summary"], "گھر گر گیا۔")

        report.status = ReportStatus.verified
        self.store.update(report)
        self.assertEqual(JsonReportStore().get(report.id).status, ReportStatus.verified)
        self.assertEqual(JsonReportStore().photo_path(report.id).read_bytes(), jpeg)
        self.assertIsNone(self.store.photo_path("../" + "ab" * 16))
        self.assertIsNone(self.store.photo_path("a" * 31))
        missing = _report("Sukkur")
        with self.assertRaises(KeyError):
            self.store.update(missing)

    def test_corrupt_file_is_not_overwritten(self):
        path = Path(self.tmp.name) / "reports.json"
        path.write_text("{not json", encoding="utf-8")
        store = JsonReportStore()
        self.assertEqual(store.count(), 0)
        with self.assertRaises(StoreWritesPaused):
            store.add(_report("Dadu"), _tiny_jpeg())
        self.assertEqual(path.read_text(encoding="utf-8"), "{not json")

    def test_schema_invalid_row_pauses_writes(self):
        good = _report("Dadu", summary="street is blocked")
        path = Path(self.tmp.name) / "reports.json"
        path.write_text(json.dumps([
            good.model_dump(mode="json"),
            {"id": "not-a-report"},
        ]), encoding="utf-8")
        store = JsonReportStore()
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.get(good.id).summary, "street is blocked")
        with self.assertRaises(StoreWritesPaused):
            store.add(_report("Sukkur"), _tiny_jpeg())
        self.assertIn("not-a-report", path.read_text(encoding="utf-8"))

    def test_relative_directory_is_next_to_the_service(self):
        import shutil

        name = "ground_reports_rel_test"
        target = SERVICE_ROOT / name
        with tempfile.TemporaryDirectory() as cwd, \
                patch.dict(os.environ, {"GROUND_REPORTS_DIR": name}):
            previous = os.getcwd()
            os.chdir(cwd)
            try:
                store = JsonReportStore()
            finally:
                os.chdir(previous)
        try:
            self.assertEqual(store.root, target.resolve())
            self.assertFalse((target / "reports.json").exists())
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_concurrent_adds_keep_every_report(self):
        from concurrent.futures import ThreadPoolExecutor

        reports = [_report("Dadu", summary=f"photo {index}") for index in range(12)]
        jpeg = _tiny_jpeg()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda report: self.store.add(report, jpeg), reports))
        reloaded = JsonReportStore()
        self.assertEqual(reloaded.count(), 12)
        self.assertEqual({item.id for item in reloaded.list()}, {item.id for item in reports})
        for report in reports:
            self.assertEqual(reloaded.photo_path(report.id).read_bytes(), jpeg)


class TestGroundReportApi(_StoreBase):
    def setUp(self):
        super().setUp()
        self.router = self.router_module.build_router(lambda _image: None)
        self.list_reports = _endpoint(self.router, "/ground-reports", "GET")
        self.get_one = _endpoint(self.router, "/ground-reports/{report_id}", "GET")
        self.photo = _endpoint(self.router, "/ground-reports/{report_id}/photo", "GET")
        self.review_report = _endpoint(self.router, "/ground-reports/{report_id}/review", "PATCH")
        self.summary = _endpoint(self.router, "/ground-summary", "GET")

    def _review(self, report_id: str, action: str, **kwargs):
        body = self.router_module.ReviewRequest(action=action, **kwargs)
        return _json(self.review_report, report_id=report_id, body=body)

    def _summary(self, district: str | None = None) -> dict:
        status, body = _json(self.summary, district=district)
        self.assertEqual(status, 200)
        return body["districts"]

    def test_list_orders_urgent_unverified_first(self):
        # Inserted out of order on purpose. Reviewed rows stay last even if urgent.
        specs = [
            ("verified-old", {"status": "verified", "created_at": "2026-01-01T00:00:00Z"}),
            ("urgent-old", {"urgent": True, "urgent_reasons": ["people_trapped"],
                            "created_at": "2026-03-01T00:00:00Z"}),
            ("rejected-mid", {"status": "rejected", "created_at": "2026-01-15T00:00:00Z"}),
            ("plain-old", {"created_at": "2026-02-01T00:00:00Z"}),
            ("corrected-urgent", {"status": "corrected", "urgent": True,
                                  "urgent_reasons": ["people_injured"],
                                  "created_at": "2026-05-01T00:00:00Z"}),
            ("urgent-new", {"urgent": True, "urgent_reasons": ["people_injured"],
                            "created_at": "2026-03-03T00:00:00Z"}),
            ("corrected-new", {"status": "corrected", "created_at": "2026-04-01T00:00:00Z"}),
            ("plain-new", {"created_at": "2026-02-02T00:00:00Z"}),
        ]
        saved = {name: self._save(**fields) for name, fields in specs}
        expected = [
            "urgent-new", "urgent-old", "plain-new", "plain-old",
            "corrected-urgent", "corrected-new", "rejected-mid", "verified-old",
        ]
        status, body = _json(self.list_reports)
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in body], [saved[name].id for name in expected])

        _, urgent_rows = _json(self.list_reports, urgent=True)
        self.assertEqual(
            [row["id"] for row in urgent_rows],
            [saved[name].id for name in ("urgent-new", "urgent-old", "corrected-urgent")],
        )
        _, unverified = _json(self.list_reports, status="unverified")
        self.assertEqual(
            [row["id"] for row in unverified],
            [saved[name].id for name in ("urgent-new", "urgent-old", "plain-new", "plain-old")],
        )
        _, rejected = _json(self.list_reports, status="rejected")
        self.assertEqual([row["id"] for row in rejected], [saved["rejected-mid"].id])
        self.assertEqual(_json(self.list_reports, district=" Sukkur ")[1], [])
        _, dadu = _json(self.list_reports, district=" Dadu ")
        self.assertEqual(len(dadu), len(expected))
        status, bad = _json(self.list_reports, status="nope")
        self.assertEqual((status, bad["code"]), (422, "invalid_status"))

    def test_duplicates_fold_under_the_first_report(self):
        urgent = self._save(urgent=True, urgent_reasons=["people_on_rooftop"],
                            created_at="2026-04-01T00:00:00Z")
        sukkur = self._save("Sukkur", created_at="2026-05-01T00:00:00Z")
        canonical = self._save(created_at="2026-01-01T00:00:00Z")
        copies = [
            self._save(created_at="2026-06-01T00:00:00Z", duplicate_of=canonical.id),
            self._save(created_at="2026-06-02T00:00:00Z", duplicate_of=canonical.id),
        ]
        status, folded = _json(self.list_reports)
        self.assertEqual(status, 200)
        self.assertEqual(_json(self.list_reports, include_duplicates=False)[1], folded)
        self.assertEqual(
            [row["id"] for row in folded],
            [urgent.id, sukkur.id, canonical.id],
        )
        by_id = {row["id"]: row for row in folded}
        self.assertEqual(by_id[canonical.id]["duplicate_count"], 2)
        self.assertEqual(by_id[urgent.id]["duplicate_count"], 0)
        self.assertEqual(by_id[sukkur.id]["duplicate_count"], 0)
        self.assertTrue(all(row["id"] not in {item.id for item in copies} for row in folded))

        _, expanded = _json(self.list_reports, include_duplicates=True)
        self.assertEqual(
            [row["id"] for row in expanded],
            [urgent.id, copies[1].id, copies[0].id, sukkur.id, canonical.id],
        )
        expanded_by_id = {row["id"]: row for row in expanded}
        self.assertEqual(expanded_by_id[copies[0].id]["duplicate_of"], canonical.id)
        self.assertEqual(expanded_by_id[canonical.id]["duplicate_count"], 0)
        self.assertEqual(JsonReportStore().get(canonical.id).duplicate_count, 0)

        _, sukkur_rows = _json(self.list_reports, district="Sukkur")
        self.assertEqual([row["id"] for row in sukkur_rows], [sukkur.id])
        _, urgent_rows = _json(self.list_reports, urgent=True)
        self.assertEqual([row["id"] for row in urgent_rows], [urgent.id])

    def test_photo_is_the_stored_jpeg(self):
        import asyncio

        jpeg = _tiny_jpeg()
        report = _report("Dadu")
        self.store.add(report, jpeg)
        response = asyncio.run(self.photo(report_id=report.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "image/jpeg")
        self.assertEqual(Path(response.path).read_bytes(), jpeg)

    def test_first_correction_snapshots_the_observation_once(self):
        report = self._save("Larkana", damage_level="none")
        self.assertIsNone(self.store.get(report.id).review.ai_original)
        status, body = self._review(
            report.id, "correct", corrections={"damage_level": "destroyed"}, officer="A",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "corrected")
        self.assertEqual(body["damage_level"], "destroyed")
        self.assertEqual(body["review"]["ai_original"]["damage_level"], "none")
        status, body = self._review(
            report.id, "correct", corrections={"damage_level": "partial"}, officer="A",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["damage_level"], "partial")
        self.assertEqual(body["review"]["ai_original"]["damage_level"], "none")
        self.assertEqual(JsonReportStore().get(report.id).review.ai_original.damage_level,
                         DamageLevel.none)

    def test_review_actions_recompute_urgent_and_drop_rejected(self):
        # other: no damage. copy: destroyed AND urgent, but it is a duplicate,
        # so it must not move the share or urgent_open. main: destroyed, person
        # on a roof, with a stale urgent=False so verify must not recompute.
        other = self._save(damage_level="none")
        self._save(
            damage_level="destroyed",
            urgent=True,
            urgent_reasons=["people_trapped"],
            duplicate_of=other.id,
        )
        main = _report(
            "Dadu",
            damage_level="destroyed",
            people={"visible": True, "on_rooftop": True},
            urgent=False,
            urgent_reasons=[],
        )
        main.review.ai_original = VlmObservation.model_validate(main.model_dump())
        self.store.add(main, _tiny_jpeg())

        dadu = self._summary()["Dadu"]
        self.assertEqual(dadu["report_count"], 2)
        self.assertEqual(dadu["photo_count"], 3)
        self.assertEqual(dadu["urgent_open"], 0)
        self.assertAlmostEqual(dadu["ground_score"], 0.5)

        status, body = self._review(
            main.id, "verify", officer="Sana", note="checked on site",
            corrections={"damage_level": "partial"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "verified")
        self.assertEqual(body["damage_level"], "destroyed")
        self.assertFalse(body["urgent"])
        self.assertEqual(body["urgent_reasons"], [])
        self.assertEqual(body["review"]["ai_original"]["damage_level"], "destroyed")
        self.assertEqual(body["review"]["ai_original"]["people"]["on_rooftop"], True)
        self.assertEqual(len(body["review"]["history"]), 1)
        self.assertEqual(body["review"]["history"][0]["action"], "verify")
        self.assertEqual(body["review"]["history"][0]["officer"], "Sana")
        self.assertEqual(body["review"]["history"][0]["note"], "checked on site")
        self.assertRegex(body["review"]["history"][0]["at"], _STAMP)
        self.assertEqual(self._summary()["Dadu"]["verified_count"], 1)
        self.assertEqual(self._summary()["Dadu"]["urgent_open"], 0)

        status, body = self._review(
            main.id, "correct", officer="Sana", note="partial, still on the roof",
            corrections={"damage_level": "partial"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "corrected")
        self.assertEqual(body["damage_level"], "partial")
        self.assertTrue(body["urgent"])
        self.assertEqual(body["urgent_reasons"], ["people_on_rooftop"])
        self.assertEqual(body["review"]["ai_original"]["damage_level"], "destroyed")
        self.assertEqual(
            [event["action"] for event in body["review"]["history"]],
            ["verify", "correct"],
        )
        dadu = self._summary()["Dadu"]
        self.assertEqual(dadu["report_count"], 2)
        self.assertEqual(dadu["photo_count"], 3)
        self.assertEqual(dadu["urgent_open"], 1)
        self.assertEqual(dadu["verified_count"], 1)
        self.assertEqual(dadu["severity_mix"], {"none": 1, "partial": 1, "destroyed": 0})
        self.assertAlmostEqual(dadu["ground_score"], 0.25)
        self.assertAlmostEqual(dadu["share_destroyed"], 0.0)
        self.assertAlmostEqual(dadu["share_damaged"], 0.5)
        self.assertEqual(
            JsonReportStore().get(main.id).urgent_reasons,
            ["people_on_rooftop"],
        )

        status, body = self._review(
            main.id, "correct", officer="Sana", note="cleared the rooftop",
            corrections={
                "people": {"visible": False, "on_rooftop": False},
                "district": " Sukkur ",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["location"]["district"], "Sukkur")
        self.assertFalse(body["urgent"])
        self.assertEqual(body["urgent_reasons"], [])
        self.assertEqual(body["damage_level"], "partial")
        self.assertFalse(body["people"]["on_rooftop"])
        self.assertTrue(body["review"]["ai_original"]["people"]["on_rooftop"])
        self.assertEqual(body["review"]["ai_original"]["damage_level"], "destroyed")
        districts = self._summary()
        self.assertEqual(districts["Dadu"]["report_count"], 1)
        self.assertEqual(districts["Dadu"]["photo_count"], 2)
        self.assertAlmostEqual(districts["Dadu"]["ground_score"], 0.0)
        self.assertEqual(districts["Dadu"]["urgent_open"], 0)
        self.assertEqual(districts["Sukkur"]["report_count"], 1)
        self.assertEqual(districts["Sukkur"]["photo_count"], 1)
        self.assertAlmostEqual(districts["Sukkur"]["ground_score"], 0.5)
        self.assertEqual(districts["Sukkur"]["verified_count"], 1)
        self.assertEqual(districts["Sukkur"]["urgent_open"], 0)
        self.assertEqual(set(self._summary(" Sukkur ")), {"Sukkur"})

        status, body = self._review(
            main.id, "reject", officer="Sana", note="not this scene",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "rejected")
        self.assertEqual(body["damage_level"], "partial")
        self.assertFalse(body["urgent"])
        self.assertEqual(
            [event["action"] for event in body["review"]["history"]],
            ["verify", "correct", "correct", "reject"],
        )
        self.assertEqual(body["review"]["history"][-1]["note"], "not this scene")
        self.assertRegex(body["review"]["history"][-1]["at"], _STAMP)
        districts = self._summary()
        self.assertNotIn("Sukkur", districts)
        self.assertEqual(districts["Dadu"]["report_count"], 1)
        self.assertEqual(districts["Dadu"]["photo_count"], 2)
        self.assertAlmostEqual(districts["Dadu"]["ground_score"], 0.0)
        self.assertEqual(districts["Dadu"]["urgent_open"], 0)
        self.assertEqual(self._summary("Sukkur"), {})

        status, fetched = _json(self.get_one, report_id=main.id)
        self.assertEqual(status, 200)
        self.assertEqual(fetched["status"], "rejected")
        saved = JsonReportStore().get(main.id)
        self.assertEqual(saved.status, ReportStatus.rejected)
        self.assertEqual(len(saved.review.history), 4)
        self.assertEqual(saved.review.ai_original.damage_level, DamageLevel.destroyed)

    def test_invalid_action_and_missing_reports(self):
        report = self._save(damage_level="partial")
        status, body = self._review(report.id, "approve", officer="Sana", note="no")
        self.assertEqual(status, 422)
        self.assertEqual(body, {
            "error": "Review action must be verify, correct, or reject.",
            "code": "invalid_action",
        })
        status, body = self._review(
            report.id, "correct", corrections={"damage_level": "nope"}, officer="Sana",
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "invalid_corrections")
        status, body = self._review(
            report.id, "correct", corrections={"summary": "officer text"}, officer="Sana",
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "invalid_corrections")
        stored = self.store.get(report.id)
        self.assertEqual(stored.status, ReportStatus.unverified)
        self.assertEqual(stored.damage_level, DamageLevel.partial)
        self.assertEqual(stored.review.history, [])

        missing = "0" * 32
        for call in (
            lambda: _json(self.get_one, report_id=missing),
            lambda: _json(self.photo, report_id=missing),
            lambda: self._review(missing, "verify", officer="Sana"),
        ):
            status, body = call()
            self.assertEqual(status, 404)
            self.assertEqual(body, {
                "error": self.router_module.NOT_FOUND_MESSAGE,
                "code": "not_found",
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
