"""Unit tests for the ground-photo intake core. No network and no model.

Run from anywhere:
    damage-checker\\.venv\\Scripts\\python.exe damage-checker\\tests\\test_ground_intake.py
"""

from __future__ import annotations

import io
import json
import os
import sys
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
    SceneType,
    VlmObservation,
    WaterDepth,
)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
