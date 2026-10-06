"""Measure POST /classify-scene on CPU: per-tile latency and peak RSS.

Forces CPU by setting CUDA_VISIBLE_DEVICES=-1 before PyTorch is imported.
Classifies synthetic scenes in-process (same code path as the endpoint).

Run from the repo root:

    $env:CUDA_VISIBLE_DEVICES="-1"
    damage-checker\\.venv\\Scripts\\python.exe scripts\\measure_classify_scene.py

Prints median and p95 seconds per tile over the 3000x3000 scene (at least
30 tiles at the default 512 px tile size), and peak RSS plus private bytes
while classifying a 3000x3000 scene and a 6000x6000 scene.
"""

from __future__ import annotations

import asyncio
import gc
import io
import json
import math
import os
import statistics
import sys
import threading
import time
from pathlib import Path

# Must be set before torch (imported by damage-checker/main.py).
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "damage-checker"
os.chdir(SERVICE)
sys.path.insert(0, str(SERVICE))

import torch  # noqa: E402
from PIL import Image  # noqa: E402
from fastapi import UploadFile  # noqa: E402

import main  # noqa: E402

TILE_SIZE = 512
SIZES = (3000, 6000)
# 3000x3000 at 512 px keeps a 6x6 grid (36 tiles): the latency sample.


def _memory_bytes() -> tuple[int, int]:
    """Return (rss, private) bytes for this process.

    On Windows, rss is the working set and private is PagefileUsage
    (committed private bytes). The working set counts mapped torch/MKL
    DLLs, so it runs hundreds of MB above the memory the scene itself
    allocates. Private bytes are what a Linux RSS limit is closer to.
    """
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        # K32GetProcessMemoryInfo takes a HANDLE. Without argtypes, ctypes
        # truncates the 64-bit handle and the call fails.
        get_mem = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        get_mem.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        get_mem.restype = wintypes.BOOL
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = get_mem(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            err = ctypes.windll.kernel32.GetLastError()
            raise OSError(f"GetProcessMemoryInfo failed (winerror {err})")
        return int(counters.WorkingSetSize), int(counters.PagefileUsage)

    import resource

    # Linux reports kilobytes; macOS reports bytes. No separate private set.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = int(value) if sys.platform == "darwin" else int(value) * 1024
    return rss, rss


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _png_bytes(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), (32, 64, 96))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image.close()
    return buf.getvalue()


def _upload(data: bytes, name: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


class _RssSampler:
    def __init__(self) -> None:
        self.peak_rss = 0
        self.peak_private = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _sample(self) -> None:
        rss, private = _memory_bytes()
        if rss > self.peak_rss:
            self.peak_rss = rss
        if private > self.peak_private:
            self.peak_private = private

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(0.02)

    def __enter__(self) -> "_RssSampler":
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._sample()


def _raise_caps(max_pixels: int) -> dict[str, str | None]:
    """Let the synthetic scenes through the endpoint caps. Restored by caller."""
    saved = {
        "SCENE_MAX_PIXELS": os.environ.get("SCENE_MAX_PIXELS"),
        "SCENE_MAX_TILES": os.environ.get("SCENE_MAX_TILES"),
        "SCENE_TIME_BUDGET_SECONDS": os.environ.get("SCENE_TIME_BUDGET_SECONDS"),
    }
    os.environ["SCENE_MAX_PIXELS"] = str(max_pixels)
    os.environ["SCENE_MAX_TILES"] = "100000"
    os.environ["SCENE_TIME_BUDGET_SECONDS"] = "3600"
    return saved


def _restore_caps(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _classify(data: bytes, name: str) -> tuple[dict, list[float], int, int]:
    durations: list[float] = []
    original = main._classify_pil

    def _timed(pil_image):
        started = time.perf_counter()
        try:
            return original(pil_image)
        finally:
            durations.append(time.perf_counter() - started)

    main._classify_pil = _timed
    try:
        with _RssSampler() as sampler:
            response = asyncio.run(main.classify_scene(
                image=_upload(data, name),
                tile_size=TILE_SIZE,
                area="bench",
            ))
        body = json.loads(response.body)
        if response.status_code != 200:
            raise RuntimeError(f"{name} failed: {response.status_code} {body}")
        return body, durations, sampler.peak_rss, sampler.peak_private
    finally:
        main._classify_pil = original


def main_measure() -> None:
    if torch.cuda.is_available():
        raise SystemExit("CUDA is available; refuse to measure on GPU")

    asyncio.run(main.startup())
    loaded_rss, loaded_private = _memory_bytes()
    # One warmup tile so the latency sample is not the first forward pass.
    warmup = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (8, 8, 8))
    main._classify_pil(warmup)
    warmup.close()
    gc.collect()

    saved = _raise_caps(max(w * h for w in SIZES for h in SIZES) + 1)
    scenes = []
    try:
        for edge in SIZES:
            gc.collect()
            png = _png_bytes(edge, edge)
            rss_before, private_before = _memory_bytes()
            body, durations, peak_rss, peak_private = _classify(
                png, f"scene_{edge}.png"
            )
            del png
            gc.collect()
            scenes.append({
                "edge": edge,
                "pixels": edge * edge,
                "tiles_classified": len(durations),
                "tile_count_response": body.get("tile_count"),
                "grid": body.get("grid"),
                "rss_before_mb": round(rss_before / (1024 * 1024), 1),
                "peak_rss_mb": round(peak_rss / (1024 * 1024), 1),
                "rss_delta_mb": round((peak_rss - rss_before) / (1024 * 1024), 1),
                "private_before_mb": round(private_before / (1024 * 1024), 1),
                "peak_private_mb": round(peak_private / (1024 * 1024), 1),
                "private_delta_mb": round(
                    (peak_private - private_before) / (1024 * 1024), 1
                ),
                "tile_seconds": durations,
            })
    finally:
        _restore_caps(saved)

    # One core, for the 0.5 vCPU slowdown. Done after the scene timings so
    # it does not change the median/p95 above.
    measured_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    single = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (8, 8, 8))
    main._classify_pil(single)
    single_durations = []
    for _ in range(8):
        started = time.perf_counter()
        main._classify_pil(single)
        single_durations.append(time.perf_counter() - started)
    single.close()

    latency_scene = scenes[0]
    durations = latency_scene["tile_seconds"]
    if len(durations) < 30:
        raise SystemExit(
            f"need at least 30 tile timings, got {len(durations)} "
            f"from the {latency_scene['edge']} scene"
        )

    summary = {
        "loaded_rss_mb": round(loaded_rss / (1024 * 1024), 1),
        "loaded_private_mb": round(loaded_private / (1024 * 1024), 1),
        "device": str(main.DEVICE),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cpu_count": os.cpu_count(),
        "torch_num_threads": measured_threads,
        "tile_size": TILE_SIZE,
        "tiles_timed": len(durations),
        "median_s": round(statistics.median(durations), 4),
        "p95_s": round(_percentile(durations, 95), 4),
        "min_s": round(min(durations), 4),
        "max_s": round(max(durations), 4),
        "single_thread_tiles": len(single_durations),
        "single_thread_median_s": round(statistics.median(single_durations), 4),
        "scenes": [
            {k: v for k, v in scene.items() if k != "tile_seconds"}
            for scene in scenes
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main_measure()
