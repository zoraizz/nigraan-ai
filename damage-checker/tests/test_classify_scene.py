"""Tests for POST /classify-scene and a /classify-damage regression.

Run from anywhere:
    damage-checker/.venv/Scripts/python.exe damage-checker/tests/test_classify_scene.py

The stitched-scene, OOD, and regression tests load the v3 checkpoint once.
Published labels below are the model predictions recorded in
sample-images/README.md (011306's ground truth is partial; the model
predicts none).
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
os.chdir(SERVICE_ROOT)
sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import UploadFile  # noqa: E402
from PIL import Image  # noqa: E402

import main  # noqa: E402

SAMPLE_DIR = SERVICE_ROOT / "sample-images"

# Published /classify-damage predictions (sample-images/README.md).
STITCH_SAMPLES = [
    ("PAKISTAN-FLOODING_018024_post_disaster.png", "none", 0.5076),
    ("PAKISTAN-FLOODING_011306_post_disaster.png", "none", 0.5922),
    ("PAKISTAN-FLOODING_014695_post_disaster.png", "destroyed", 0.5406),
]
JOPLIN = ("joplin-tornado_00000120_post_disaster.png", "destroyed", 0.9849)
# Narrower than half of the default 512 px tile, so the last column is skipped.
RAGGED_PX = 200


def _run(coro):
    return asyncio.run(coro)


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _upload(data: bytes, name: str = "scene.png") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


def _payload(response):
    return response.status_code, json.loads(response.body)


class TestTilePlan(unittest.TestCase):
    def test_skips_ragged_edge_under_half(self):
        plan = main._plan_tiles(600, 600, 512)
        self.assertEqual(plan["rows"], 2)
        self.assertEqual(plan["cols"], 2)
        self.assertEqual(plan["skipped_count"], 3)
        self.assertEqual(plan["tile_count"], 1)
        self.assertEqual(plan["kept"][0]["x"], 0)
        self.assertEqual(plan["kept"][0]["y"], 0)

    def test_keeps_remainder_of_exactly_half(self):
        plan = main._plan_tiles(512 + 256, 512, 512)
        self.assertEqual(plan["tile_count"], 2)
        self.assertEqual(plan["skipped_count"], 0)

    def test_skips_remainder_just_under_half(self):
        plan = main._plan_tiles(512 + 255, 512, 512)
        self.assertEqual(plan["tile_count"], 1)
        self.assertEqual(plan["skipped_count"], 1)


class TestClassifyScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _run(main.startup())
        paths = {getattr(route, "path", None) for route in main.app.routes}
        if "/classify-scene" not in paths or "/classify-damage" not in paths:
            raise RuntimeError(f"routes missing classify endpoints: {paths}")
        if not main._model_loaded:
            raise RuntimeError(f"checkpoint not loaded from {main.CHECKPOINT_PATH}")
        if main._ood_reference is None:
            raise RuntimeError("ood_reference.json is required for the OOD test")

    def test_stitched_sample_scene(self):
        images = []
        for name, _label, _confidence in STITCH_SAMPLES:
            image = Image.open(SAMPLE_DIR / name).convert("RGB")
            self.assertEqual(image.size, (512, 512), name)
            images.append(image)

        canvas = Image.new("RGB", (512 * len(images) + RAGGED_PX, 512))
        for index, image in enumerate(images):
            canvas.paste(image, (index * 512, 0))
            image.close()

        status, body = _payload(_run(main.classify_scene(
            image=_upload(_png_bytes(canvas), "stitched.png"),
            tile_size=512,
            area="Sindh",
        )))
        canvas.close()
        print("STITCHED_SCENE_RESPONSE")
        print(json.dumps(body, indent=2))

        self.assertEqual(status, 200)
        self.assertEqual(body["tile_size"], 512)
        self.assertEqual(body["grid"], {"rows": 1, "cols": 4})
        self.assertEqual(body["tile_count"], 3)
        self.assertEqual(body["skipped_count"], 1)
        self.assertEqual(body["area"], "Sindh")
        self.assertEqual(len(body["tiles"]), 3)

        breakdown = {"none": 0, "partial": 0, "destroyed": 0, "uncertain": 0}
        for tile, (name, label, confidence) in zip(body["tiles"], STITCH_SAMPLES):
            single_status, single = _payload(_run(main.classify_damage(
                image=_upload((SAMPLE_DIR / name).read_bytes(), name),
                area="Sindh",
            )))
            self.assertEqual(single_status, 200)
            self.assertEqual(single["damage_level"], label, name)
            self.assertEqual(single["confidence"], confidence, name)
            self.assertEqual(tile["label"], label, name)
            self.assertEqual(tile["confidence"], confidence, name)
            self.assertFalse(tile["uncertain"])
            self.assertEqual(set(tile.keys()), {
                "row", "col", "x", "y", "label", "confidence", "uncertain",
            })
            breakdown[label] += 1

        self.assertEqual(body["damage_breakdown"], breakdown)
        classified = breakdown["none"] + breakdown["partial"] + breakdown["destroyed"]
        self.assertEqual(
            body["percent_damaged"],
            round((breakdown["partial"] + breakdown["destroyed"]) / classified, 4),
        )
        self.assertEqual(body["overall_damage_level"], "destroyed")
        self.assertEqual(body["tiles"][0]["x"], 0)
        self.assertEqual(body["tiles"][1]["x"], 512)
        self.assertEqual(body["tiles"][2]["x"], 1024)
        self.assertNotIn("image", json.dumps(body))

    def test_ood_tile_is_uncertain(self):
        sample_name = STITCH_SAMPLES[0][0]
        sample = Image.open(SAMPLE_DIR / sample_name).convert("RGB")
        canvas = Image.new("RGB", (1024, 512), (255, 0, 0))
        canvas.paste(sample, (0, 0))
        sample.close()

        status, body = _payload(_run(main.classify_scene(
            image=_upload(_png_bytes(canvas), "ood-scene.png"),
            tile_size=512,
            area="unknown",
        )))
        canvas.close()

        self.assertEqual(status, 200)
        self.assertEqual(body["grid"], {"rows": 1, "cols": 2})
        self.assertEqual(body["tile_count"], 2)
        self.assertEqual(body["skipped_count"], 0)

        real, solid = body["tiles"]
        self.assertEqual(real["label"], STITCH_SAMPLES[0][1])
        self.assertFalse(real["uncertain"])
        self.assertTrue(solid["uncertain"])
        self.assertEqual(solid["label"], "uncertain")
        self.assertEqual(solid["col"], 1)

        breakdown = body["damage_breakdown"]
        self.assertEqual(breakdown["uncertain"], 1)
        self.assertEqual(breakdown["none"], 1)
        self.assertEqual(breakdown["partial"], 0)
        self.assertEqual(breakdown["destroyed"], 0)
        self.assertEqual(body["percent_damaged"], 0.0)
        self.assertEqual(body["overall_damage_level"], "none")

    def test_oversized_image_rejected(self):
        previous_cap = Image.MAX_IMAGE_PIXELS
        self.assertIsNotNone(previous_cap)
        oversized = _png_bytes(Image.new("RGB", (40, 40), (0, 0, 0)))
        old = os.environ.get("SCENE_MAX_PIXELS")
        os.environ["SCENE_MAX_PIXELS"] = "1000"
        try:
            status, body = _payload(_run(main.classify_scene(
                image=_upload(oversized, "big.png"),
                tile_size=512,
                area="unknown",
            )))
        finally:
            if old is None:
                os.environ.pop("SCENE_MAX_PIXELS", None)
            else:
                os.environ["SCENE_MAX_PIXELS"] = old

        self.assertEqual(status, 413)
        self.assertEqual(body["code"], "image_too_large")
        self.assertIn("1600", body["error"])
        self.assertIn("1000", body["error"])
        self.assertIsNotNone(Image.MAX_IMAGE_PIXELS)
        self.assertEqual(Image.MAX_IMAGE_PIXELS, previous_cap)

    def test_too_many_tiles_rejected(self):
        scene = _png_bytes(Image.new("RGB", (1024, 512), (10, 20, 30)))
        old = os.environ.get("SCENE_MAX_TILES")
        os.environ["SCENE_MAX_TILES"] = "1"
        try:
            status, body = _payload(_run(main.classify_scene(
                image=_upload(scene, "many.png"),
                tile_size=512,
                area="unknown",
            )))
        finally:
            if old is None:
                os.environ.pop("SCENE_MAX_TILES", None)
            else:
                os.environ["SCENE_MAX_TILES"] = old

        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "too_many_tiles")
        self.assertIn("2 tiles", body["error"])

    def test_time_budget_zero_returns_no_tiles(self):
        scene = _png_bytes(Image.new("RGB", (1024, 512), (10, 20, 30)))
        old = os.environ.get("SCENE_TIME_BUDGET_SECONDS")
        os.environ["SCENE_TIME_BUDGET_SECONDS"] = "0"
        try:
            status, body = _payload(_run(main.classify_scene(
                image=_upload(scene, "budget.png"),
                tile_size=512,
                area="Sindh",
            )))
        finally:
            if old is None:
                os.environ.pop("SCENE_TIME_BUDGET_SECONDS", None)
            else:
                os.environ["SCENE_TIME_BUDGET_SECONDS"] = old

        self.assertEqual(status, 200)
        self.assertIs(body["truncated"], True)
        self.assertEqual(body["tiles_processed"], 0)
        self.assertEqual(body["tiles_total"], 2)
        self.assertEqual(body["tile_count"], 0)
        self.assertEqual(body["tiles"], [])
        self.assertEqual(body["skipped_count"], 0)
        self.assertEqual(
            body["damage_breakdown"],
            {"none": 0, "partial": 0, "destroyed": 0, "uncertain": 0},
        )
        self.assertIsNone(body["percent_damaged"])
        self.assertIsNone(body["overall_damage_level"])
        self.assertEqual(body["area"], "Sindh")

    def test_time_budget_stops_after_one_tile(self):
        sample_name, label, confidence = STITCH_SAMPLES[0]
        sample = Image.open(SAMPLE_DIR / sample_name).convert("RGB")
        canvas = Image.new("RGB", (1024, 512), (255, 0, 0))
        canvas.paste(sample, (0, 0))
        sample.close()
        scene = _png_bytes(canvas)
        canvas.close()

        # start, check before tile 0 (elapsed 0), check before tile 1 (over).
        clocks = iter([1000.0, 1000.0, 1050.0])
        original_clock = main._scene_clock
        main._scene_clock = lambda: next(clocks)
        old = os.environ.get("SCENE_TIME_BUDGET_SECONDS")
        os.environ["SCENE_TIME_BUDGET_SECONDS"] = "40"
        try:
            status, body = _payload(_run(main.classify_scene(
                image=_upload(scene, "partial-budget.png"),
                tile_size=512,
                area="unknown",
            )))
        finally:
            main._scene_clock = original_clock
            if old is None:
                os.environ.pop("SCENE_TIME_BUDGET_SECONDS", None)
            else:
                os.environ["SCENE_TIME_BUDGET_SECONDS"] = old

        self.assertEqual(status, 200)
        self.assertIs(body["truncated"], True)
        self.assertEqual(body["tiles_processed"], 1)
        self.assertEqual(body["tiles_total"], 2)
        self.assertEqual(body["tile_count"], 1)
        self.assertEqual(len(body["tiles"]), 1)
        single_status, single = _payload(_run(main.classify_damage(
            image=_upload((SAMPLE_DIR / sample_name).read_bytes(), sample_name),
            area="unknown",
        )))
        self.assertEqual(single_status, 200)
        tile = body["tiles"][0]
        self.assertEqual(tile["label"], single["damage_level"])
        self.assertEqual(tile["confidence"], single["confidence"])
        self.assertEqual(tile["label"], label)
        self.assertEqual(tile["confidence"], confidence)
        self.assertFalse(tile["uncertain"])
        self.assertEqual(tile["col"], 0)
        self.assertEqual(body["damage_breakdown"]["none"], 1)
        self.assertEqual(body["damage_breakdown"]["uncertain"], 0)
        self.assertEqual(body["percent_damaged"], 0.0)
        self.assertEqual(body["overall_damage_level"], "none")

    def test_within_budget_is_not_truncated(self):
        scene = _png_bytes(Image.new("RGB", (512, 512), (10, 20, 30)))
        old = os.environ.get("SCENE_TIME_BUDGET_SECONDS")
        os.environ.pop("SCENE_TIME_BUDGET_SECONDS", None)
        try:
            status, body = _payload(_run(main.classify_scene(
                image=_upload(scene, "full.png"),
                tile_size=512,
                area="unknown",
            )))
        finally:
            if old is not None:
                os.environ["SCENE_TIME_BUDGET_SECONDS"] = old

        self.assertEqual(status, 200)
        self.assertIs(body["truncated"], False)
        self.assertEqual(body["tiles_processed"], 1)
        self.assertEqual(body["tiles_total"], 1)
        self.assertEqual(body["tile_count"], body["tiles_processed"])
        self.assertEqual(len(body["tiles"]), 1)

    def test_classify_damage_output_unchanged(self):
        name, label, confidence = JOPLIN
        status, body = _payload(_run(main.classify_damage(
            image=_upload((SAMPLE_DIR / name).read_bytes(), name),
            area="unknown",
        )))
        again_status, again = _payload(_run(main.classify_damage(
            image=_upload((SAMPLE_DIR / name).read_bytes(), name),
            area="unknown",
        )))

        self.assertEqual(status, 200)
        self.assertEqual(again_status, 200)
        self.assertEqual(body, again)
        self.assertEqual(body["damage_level"], label)
        self.assertEqual(body["confidence"], confidence)
        self.assertEqual(body["area"], "unknown")
        self.assertIs(body["is_out_of_domain"], False)
        self.assertEqual(body["ood"]["signals"], [])
        self.assertNotIn("classification", body)
        self.assertNotIn("message", body)
        self.assertEqual(
            set(body.keys()),
            {"damage_level", "confidence", "area", "is_out_of_domain", "ood"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
