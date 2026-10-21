"""Build the Indus centreline and the Taunsa–Kotri floodplain village table.

This is an offline batch script. It downloads OpenStreetMap, UNOSAT, OCHA and
WorldPop inputs into a cache directory, then writes:

- flood-tracker/data/indus.geojson
- flood-tracker/data/villages.json

A second run reuses the cache and does not call the network. Nothing here is a
gauge reading. Populations are WorldPop grid estimates.

Formulas
--------
Centreline. OpenStreetMap ways tagged waterway=river and name/name:en matching
"Indus", inside the Pakistan reach that covers Tarbela and the delta. Ways are
projected to EPSG:32642 (WGS 84 / UTM zone 42N). Endpoints within 200 m are
treated as the same junction. The published line is the shortest path along
that network from the junction nearest Tarbela Dam to the junction nearest the
river mouth, then cut to the nearest point to Tarbela Dam and the nearest point
to Kotri Barrage. Shortest path is used so a side channel that rejoins the
river cannot pull the centreline off the stem that passes the barrages. UTM is
only for topology and simplification. Zone 42 distortion on this reach is well
under one percent.

Simplification. Douglas–Peucker (Shapely ``simplify``) in UTM metres. The
tolerance is binary-searched so the vertex count is as close as possible to
300. Endpoints are kept, so the line still starts at Tarbela and ends at Kotri.

river_km. Cumulative WGS84 geodesic length (pyproj.Geod, inverse) along the
simplified line. properties.river_km_start is 0 at the Tarbela end.
properties.river_km[i] is the kilometre of vertex i. A village's river_km is
the value at its closest point on that line: the nearest segment in UTM, then
linear interpolation of the geodesic kilometre by the fraction along that
segment.

Bank. Facing downstream (increasing river_km). In the UTM plane, x is east and
y is north. For a segment direction (dx, dy) and a vector from the segment
start to the village (vx, vy), the cross product dx*vy - dy*vx is positive on
the left bank and negative on the right bank. A point exactly on the segment
is labelled left.

15 km filter. Distance from the village to the Taunsa–Kotri portion of the
centreline, measured in EPSG:32642. Villages with distance <= 15 km are kept.
The portion is the centreline from the nearest point to Taunsa Barrage through
the Kotri end, including the round cap at Taunsa that a 15 km distance implies.

Flood filter. The village point must intersect the UNOSAT VIIRS cumulative
flood-water polygon for Pakistan, 1 July–31 August 2022 (HDX). This is detected
water, including breach flooding away from the channel. It is not a forecast
from the barrage routing model.

Population. WorldPop unconstrained Pakistan 2020, 100 m (3 arc-second) people
per pixel. For each kept settlement, sum the pixel values whose centres fall
inside a 1 km radius circle drawn in EPSG:32642 and transformed back to the
raster CRS. Nodata and negative values are ignored. The sum is rounded to the
nearest integer. This is people estimated on the grid within 1 km of the
OpenStreetMap node, not a census count of that named place. population_source
is the fixed label "WorldPop 2020 estimate".

District. OCHA COD-AB Pakistan admin level 2. A settlement inside a district
polygon takes that district (distance 0, which is the nearest). A settlement
outside every polygon takes the nearest district polygon.

Anchors (structure locations used to cut the line, not gauge coordinates):
Tarbela Dam 34.089722 N, 72.698333 E; Taunsa Barrage 30.51278 N, 70.84917 E;
Kotri Barrage 25.44222 N, 68.31667 E.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
import shapely
from pyproj import Geod, Transformer
from rasterio.features import geometry_mask
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import linemerge, substring, unary_union
from shapely.prepared import prep

LOG = logging.getLogger("flood.villages")

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "flood-tracker" / "data"
INDUS_PATH = DATA_DIR / "indus.geojson"
VILLAGES_PATH = DATA_DIR / "villages.json"

USER_AGENT = "nigraan-flood-tracker/1.0 (village build; educational disaster demo)"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)

FLOOD_URL = (
    "https://data.humdata.org/dataset/f685e623-a539-4af0-92ff-19b737ec95b3/"
    "resource/fa89ec39-8dd0-4abe-b97e-0a3d9e9627a5/download/"
    "viirs_20220701_20220831_floodextent_pak.zip"
)
ADMIN_URL = (
    "https://data.humdata.org/dataset/a64d1ff2-7158-48c7-887d-6af69ce21906/"
    "resource/d2752403-3c34-4e03-8b4e-3e55500ded10/download/"
    "pak_admin_boundaries.shp.zip"
)
WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/PAK/"
    "pak_ppp_2020.tif"
)

# (lon, lat). See the module docstring for the sources.
TARBELA = (72.698333, 34.089722)
KALABAGH = (71.546, 32.961)
CHASHMA = (71.39, 32.45)
TAUNSA = (70.84917, 30.51278)
GUDDU = (69.715, 28.42)
SUKKUR = (68.859, 27.699)
KOTRI = (68.31667, 25.44222)
ANCHORS = (
    ("Tarbela", TARBELA),
    ("Kalabagh", KALABAGH),
    ("Chashma", CHASHMA),
    ("Taunsa", TAUNSA),
    ("Guddu", GUDDU),
    ("Sukkur", SUKKUR),
    ("Kotri", KOTRI),
)

INDUS_BBOX = (24.7, 67.2, 34.8, 73.9)  # south, west, north, east
SNAP_M = 200.0
CORRIDOR_M = 15_000.0
POP_RADIUS_M = 1_000.0
TARGET_VERTICES = 300
UTM = "EPSG:32642"
GEOD = Geod(ellps="WGS84")
TO_UTM = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
TO_WGS = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)

FLOOD_SOURCE = (
    "UNOSAT VIIRS cumulative satellite-detected flood water, Pakistan, "
    "1 July-31 August 2022 (HDX viirs_20220701_20220831_floodextent_pak, "
    "event FL20220808PAK)"
)
WORLDPOP_SOURCE = (
    "WorldPop unconstrained Pakistan 2020 100 m people-per-pixel "
    "(pak_ppp_2020.tif), summed inside a 1 km radius of the settlement node"
)
ADMIN_SOURCE = (
    "OCHA COD-AB Pakistan admin level 2 districts (HDX cod-ab-pak, pak_admin2)"
)
RIVER_SOURCE = (
    "river_km is the WGS84 geodesic projection onto flood-tracker/data/indus.geojson "
    "(OpenStreetMap waterway=river name matching Indus, cut at Tarbela Dam and Kotri Barrage)"
)
POPULATION_SOURCE = "WorldPop 2020 estimate"


def default_cache() -> Path:
    env = os.environ.get("FLOOD_GEO_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "nigraan-flood-geo"


def download(url: str, dest: Path, minimum_bytes: int = 1) -> None:
    if dest.exists() and dest.stat().st_size >= minimum_bytes:
        LOG.info("cache hit %s (%s bytes)", dest.name, dest.stat().st_size)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    LOG.info("downloading %s", url)
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": USER_AGENT}) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if partial.stat().st_size < minimum_bytes:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"download too small: {url}")
    partial.replace(dest)
    LOG.info("saved %s (%s bytes)", dest.name, dest.stat().st_size)


def overpass(query: str) -> dict:
    last_error = "no attempt"
    for attempt in range(6):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            response = requests.post(
                endpoint,
                data=query.encode("utf-8"),
                headers={"User-Agent": USER_AGENT},
                timeout=200,
            )
        except requests.RequestException as exc:
            last_error = f"{endpoint}: {exc}"
            LOG.warning("overpass error %s", last_error)
            time.sleep(min(2 ** attempt, 20))
            continue
        if response.status_code == 200 and response.text.lstrip().startswith("{"):
            return response.json()
        last_error = f"{endpoint}: HTTP {response.status_code} {response.text[:180]}"
        LOG.warning("overpass rejected %s", last_error)
        time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Overpass failed: {last_error}")


def fetch_indus_ways(cache: Path) -> list[dict]:
    dest = cache / "osm_indus_ways.json"
    if dest.exists() and dest.stat().st_size > 1000:
        LOG.info("cache hit %s", dest.name)
        return json.loads(dest.read_text(encoding="utf-8"))["elements"]
    south, west, north, east = INDUS_BBOX
    query = f"""[out:json][timeout:180];
(
  way["waterway"="river"]["name"~"Indus",i]({south},{west},{north},{east});
  way["waterway"="river"]["name:en"~"Indus",i]({south},{west},{north},{east});
);
out geom;
"""
    payload = overpass(query)
    dest.write_text(json.dumps(payload), encoding="utf-8")
    LOG.info("Indus ways %s", len(payload.get("elements", [])))
    return payload["elements"]


def _as_lines(elements: list[dict]) -> list[LineString]:
    lines = []
    for element in elements:
        coords = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
        if len(coords) >= 2:
            lines.append(LineString(coords))
    if not lines:
        raise RuntimeError("OpenStreetMap returned no Indus ways")
    return lines


def _projected(line: LineString) -> LineString:
    return LineString([TO_UTM.transform(lon, lat) for lon, lat in line.coords])


def _geographic(line: LineString) -> LineString:
    return LineString([TO_WGS.transform(x, y) for x, y in line.coords])


class _RiverGraph:
    def __init__(self, parts: list[LineString]) -> None:
        self.parts = [_projected(part) for part in parts]
        self.endpoints: list[tuple[float, float, int, bool]] = []
        for index, part in enumerate(self.parts):
            self.endpoints.append((part.coords[0][0], part.coords[0][1], index, False))
            self.endpoints.append((part.coords[-1][0], part.coords[-1][1], index, True))
        parent = list(range(len(self.endpoints)))

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(left: int, right: int) -> None:
            left, right = find(left), find(right)
            if left != right:
                parent[right] = left

        snap2 = SNAP_M * SNAP_M
        for left in range(len(self.endpoints)):
            lx, ly = self.endpoints[left][0], self.endpoints[left][1]
            for right in range(left + 1, len(self.endpoints)):
                dx = lx - self.endpoints[right][0]
                dy = ly - self.endpoints[right][1]
                if dx * dx + dy * dy <= snap2:
                    union(left, right)
        self.node_of: dict[tuple[int, bool], int] = {}
        for index, (_x, _y, part_index, is_end) in enumerate(self.endpoints):
            self.node_of[(part_index, is_end)] = find(index)
        self.adj: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
        for index, part in enumerate(self.parts):
            start = self.node_of[(index, False)]
            end = self.node_of[(index, True)]
            weight = part.length
            self.adj[start].append((end, index, weight))
            self.adj[end].append((start, index, weight))

    def nearest_node(self, lon: float, lat: float) -> tuple[int, float]:
        x, y = TO_UTM.transform(lon, lat)
        best_node = None
        best_distance = float("inf")
        for ex, ey, part_index, is_end in self.endpoints:
            distance = ((ex - x) ** 2 + (ey - y) ** 2) ** 0.5
            if distance < best_distance:
                best_distance = distance
                best_node = self.node_of[(part_index, is_end)]
        if best_node is None:
            raise RuntimeError("river graph has no endpoints")
        return best_node, best_distance

    def component(self, start: int) -> set[int]:
        seen = {start}
        stack = [start]
        while stack:
            node = stack.pop()
            for neighbour, _edge, _weight in self.adj[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        return seen

    def southern_node(self, nodes: set[int]) -> int:
        best_node = None
        best_lat = float("inf")
        for ex, ey, part_index, is_end in self.endpoints:
            node = self.node_of[(part_index, is_end)]
            if node not in nodes:
                continue
            _lon, lat = TO_WGS.transform(ex, ey)
            if lat < best_lat:
                best_lat = lat
                best_node = node
        if best_node is None:
            raise RuntimeError("no southern node on the Indus component")
        return best_node

    def shortest_path(self, source: int, target: int) -> list[int]:
        import heapq

        distance = {source: 0.0}
        previous: dict[int, tuple[int, int]] = {}
        heap = [(0.0, source)]
        while heap:
            current, node = heapq.heappop(heap)
            if current != distance.get(node):
                continue
            if node == target:
                break
            for neighbour, edge, weight in self.adj[node]:
                proposed = current + weight
                if proposed < distance.get(neighbour, float("inf")):
                    distance[neighbour] = proposed
                    previous[neighbour] = (node, edge)
                    heapq.heappush(heap, (proposed, neighbour))
        if target not in distance:
            raise RuntimeError("no path from Tarbela to the Indus mouth on the OSM centreline")
        edges: list[int] = []
        node = target
        while node != source:
            node, edge = previous[node]
            edges.append(edge)
        edges.reverse()
        return edges

    def assemble(self, source: int, edges: list[int]) -> LineString:
        coordinates: list[tuple[float, float]] = []
        node = source
        for edge in edges:
            part = self.parts[edge]
            forward = self.node_of[(edge, False)] == node
            sequence = list(part.coords if forward else reversed(part.coords))
            if coordinates and sequence:
                if abs(coordinates[-1][0] - sequence[0][0]) < 1 and abs(coordinates[-1][1] - sequence[0][1]) < 1:
                    sequence = sequence[1:]
            coordinates.extend(sequence)
            node = self.node_of[(edge, True if forward else False)]
        if len(coordinates) < 2:
            raise RuntimeError("assembled Indus centreline is empty")
        return LineString(coordinates)


def build_raw_centreline(elements: list[dict]) -> LineString:
    """Return the dam-to-mouth centreline in UTM metres."""
    merged = linemerge(unary_union(_as_lines(elements)))
    parts = list(merged.geoms) if merged.geom_type == "MultiLineString" else [merged]
    graph = _RiverGraph(parts)
    tarbela_node, tarbela_gap = graph.nearest_node(*TARBELA)
    if tarbela_gap > 5_000:
        raise RuntimeError(f"Tarbela is {tarbela_gap:.0f} m from the OSM Indus line")
    mouth = graph.southern_node(graph.component(tarbela_node))
    edges = graph.shortest_path(tarbela_node, mouth)
    line = graph.assemble(tarbela_node, edges)
    LOG.info(
        "raw centreline %.1f km UTM, %s vertices, Tarbela junction %.0f m from the dam anchor",
        line.length / 1000,
        len(line.coords),
        tarbela_gap,
    )
    return line


def cut_tarbela_to_kotri(line_m: LineString) -> LineString:
    start = line_m.project(Point(TO_UTM.transform(*TARBELA)))
    end = line_m.project(Point(TO_UTM.transform(*KOTRI)))
    if end <= start:
        raise RuntimeError(f"Kotri along-track {end:.0f} m is not downstream of Tarbela {start:.0f} m")
    cut = substring(line_m, start, end)
    if cut.geom_type != "LineString" or cut.is_empty:
        raise RuntimeError(f"cut centreline has geometry {cut.geom_type}")
    LOG.info("cut Tarbela to Kotri %.1f km UTM", cut.length / 1000)
    return cut


def simplify_to_about(line_m: LineString, target: int = TARGET_VERTICES) -> LineString:
    count = len(line_m.coords)
    if count <= target:
        return line_m
    low, high = 0.0, 20_000.0
    best = line_m
    best_gap = abs(count - target)
    for _ in range(28):
        tolerance = (low + high) / 2
        simplified = line_m.simplify(tolerance, preserve_topology=False)
        simplified_count = len(simplified.coords)
        gap = abs(simplified_count - target)
        if gap < best_gap and simplified_count >= 2:
            best = simplified
            best_gap = gap
        if simplified_count > target:
            low = tolerance
        else:
            high = tolerance
    LOG.info("simplified to %s vertices (target %s)", len(best.coords), target)
    return best


def geodesic_km(line_wgs: LineString) -> list[float]:
    kilometres = [0.0]
    coords = list(line_wgs.coords)
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        _az1, _az2, metres = GEOD.inv(lon1, lat1, lon2, lat2)
        kilometres.append(kilometres[-1] + metres / 1000.0)
    return kilometres


def anchor_report(line_m: LineString) -> list[tuple[str, float, float]]:
    rows = []
    for name, (lon, lat) in ANCHORS:
        point = Point(TO_UTM.transform(lon, lat))
        rows.append((name, line_m.distance(point), line_m.project(point) / 1000.0))
    for name, distance_m, along_km in rows:
        LOG.info("anchor %-10s %7.0f m from line, UTM along %.1f km", name, distance_m, along_km)
    return rows


def write_indus(line_wgs: LineString) -> dict:
    coordinates = [[round(lon, 6), round(lat, 6)] for lon, lat in line_wgs.coords]
    # Recompute kilometres on the rounded coordinates that are actually published.
    published = geodesic_km(LineString(coordinates))
    feature = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Indus",
                    "river_km_start": 0,
                    "river_km_end": round(published[-1], 3),
                    "river_km": [round(value, 3) for value in published],
                    "source": (
                        "OpenStreetMap ways tagged waterway=river with name or name:en "
                        "matching Indus. Cut from the nearest point to Tarbela Dam "
                        "(34.089722 N, 72.698333 E) to the nearest point to Kotri Barrage "
                        "(25.44222 N, 68.31667 E). Douglas-Peucker simplified to about 300 vertices. "
                        "river_km is cumulative WGS84 geodesic kilometres from Tarbela."
                    ),
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        ],
    }
    INDUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDUS_PATH.write_text(json.dumps(feature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("wrote %s (%.1f km, %s vertices)", INDUS_PATH, published[-1], len(coordinates))
    return feature


def load_published_line() -> tuple[LineString, list[float], LineString]:
    payload = json.loads(INDUS_PATH.read_text(encoding="utf-8"))
    geometry = shape(payload["features"][0]["geometry"])
    kilometres = [float(value) for value in payload["features"][0]["properties"]["river_km"]]
    return geometry, kilometres, _projected(geometry)


def taunsa_kotri_portion(line_m: LineString) -> LineString:
    start = line_m.project(Point(TO_UTM.transform(*TAUNSA)))
    portion = substring(line_m, start, line_m.length)
    if portion.is_empty or portion.geom_type != "LineString":
        raise RuntimeError("Taunsa–Kotri portion could not be cut")
    return portion


def project_onto(line_m: LineString, kilometres: list[float], lon: float, lat: float) -> tuple[float, str, float]:
    """Return river_km, bank, and UTM distance in metres to the closest point."""
    x, y = TO_UTM.transform(lon, lat)
    coords = list(line_m.coords)
    best_distance2 = float("inf")
    best_km = 0.0
    best_cross = 0.0
    for index in range(len(coords) - 1):
        ax, ay = coords[index]
        bx, by = coords[index + 1]
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 == 0:
            continue
        fraction = ((x - ax) * dx + (y - ay) * dy) / length2
        fraction = min(1.0, max(0.0, fraction))
        px, py = ax + fraction * dx, ay + fraction * dy
        distance2 = (x - px) ** 2 + (y - py) ** 2
        if distance2 < best_distance2:
            best_distance2 = distance2
            best_cross = dx * (y - ay) - dy * (x - ax)
            best_km = kilometres[index] + fraction * (kilometres[index + 1] - kilometres[index])
    bank = "left" if best_cross >= 0 else "right"
    return best_km, bank, best_distance2 ** 0.5


def distance_to_line(line_m: LineString, lon: float, lat: float) -> float:
    x, y = TO_UTM.transform(lon, lat)
    return line_m.distance(Point(x, y))


def fetch_settlements(cache: Path, west: float, south: float, east: float, north: float) -> list[dict]:
    cache.mkdir(parents=True, exist_ok=True)
    collected: dict[tuple[str, int], dict] = {}
    lat = south
    while lat < north - 1e-9:
        lat2 = min(north, lat + 1.0)
        band = cache / f"osm_places_{lat:.2f}_{lat2:.2f}_{west:.2f}_{east:.2f}.json"
        if band.exists() and band.stat().st_size > 2:
            payload = json.loads(band.read_text(encoding="utf-8"))
            LOG.info("cache hit %s (%s elements)", band.name, len(payload["elements"]))
        else:
            query = f"""[out:json][timeout:180];
(
  node["place"~"^(village|town|city)$"]({lat:.6f},{west:.6f},{lat2:.6f},{east:.6f});
  way["place"~"^(village|town|city)$"]({lat:.6f},{west:.6f},{lat2:.6f},{east:.6f});
  relation["place"~"^(village|town|city)$"]({lat:.6f},{west:.6f},{lat2:.6f},{east:.6f});
);
out tags center;
"""
            payload = overpass(query)
            band.write_text(json.dumps(payload), encoding="utf-8")
            LOG.info("settlement band %.2f–%.2f returned %s", lat, lat2, len(payload.get("elements", [])))
            time.sleep(1)
        for element in payload.get("elements", []):
            collected[(element["type"], element["id"])] = element
        lat = lat2
    return list(collected.values())


def element_lonlat(element: dict) -> tuple[float, float] | None:
    if "lon" in element and "lat" in element:
        return float(element["lon"]), float(element["lat"])
    center = element.get("center") or {}
    if "lon" in center and "lat" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def settlement_name(tags: dict) -> str:
    english = (tags.get("name:en") or "").strip()
    if english:
        return english
    return (tags.get("name") or "").strip()


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return ascii_text


def load_flood(cache: Path):
    frame = gpd.read_file(cache / "viirs_flood.zip")
    if frame.crs is None:
        frame = frame.set_crs(4326)
    else:
        frame = frame.to_crs(4326)
    geometry = unary_union(frame.geometry)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    LOG.info("flood extent area roughly %.0f km2 in EPSG:6933", gpd.GeoSeries([geometry], crs=4326).to_crs(6933).area.sum() / 1e6)
    return prep(geometry), geometry


def load_admin(cache: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(cache / "pak_admin_boundaries.shp.zip", layer="pak_admin2")
    if frame.crs is None:
        frame = frame.set_crs(4326)
    else:
        frame = frame.to_crs(4326)
    frame["adm2_name"] = frame["adm2_name"].astype(str).str.strip()
    return frame[["adm2_name", "geometry"]].reset_index(drop=True)


def _utm_xy_to_lonlat(coords: np.ndarray) -> np.ndarray:
    lon, lat = TO_WGS.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([lon, lat])


def population_within_1km(dataset: rasterio.DatasetReader, lon: float, lat: float) -> int:
    x, y = TO_UTM.transform(lon, lat)
    circle_m = Point(x, y).buffer(POP_RADIUS_M, resolution=12)
    circle = shapely.transform(circle_m, _utm_xy_to_lonlat)
    window = rasterio.windows.from_bounds(*circle.bounds, transform=dataset.transform)
    window = window.round_offsets().round_lengths()
    window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
    if window.width <= 0 or window.height <= 0:
        return 0
    data = dataset.read(1, window=window, masked=True)
    if data.size == 0:
        return 0
    inside = geometry_mask(
        [mapping(circle)],
        out_shape=data.shape,
        transform=dataset.window_transform(window),
        invert=True,
    )
    values = data[inside]
    total = np.ma.sum(values)
    if np.ma.is_masked(total):
        return 0
    total = float(total)
    if not np.isfinite(total) or total < 0:
        return 0
    return int(np.rint(total))


def assign_districts(points: gpd.GeoDataFrame, admin: gpd.GeoDataFrame) -> list[str]:
    joined = gpd.sjoin(points, admin, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    names = joined["adm2_name"].tolist()
    missing = [index for index, name in enumerate(names) if not isinstance(name, str) or not name or name == "nan"]
    if missing:
        orphans = points.iloc[missing]
        nearest = gpd.sjoin_nearest(orphans, admin, how="left")
        nearest = nearest[~nearest.index.duplicated(keep="first")]
        for row_index, name in zip(missing, nearest["adm2_name"].tolist()):
            names[row_index] = name if isinstance(name, str) else ""
        LOG.info("district nearest-fill for %s settlements outside every admin-2 polygon", len(missing))
    if any(not name for name in names):
        raise RuntimeError("a settlement has no admin-2 district")
    return [str(name) for name in names]


def build_village_rows(cache: Path) -> list[dict]:
    _line_wgs, kilometres, line_m = load_published_line()
    portion = taunsa_kotri_portion(line_m)
    bounds = _geographic(portion).bounds  # minx, miny, maxx, maxy
    pad = 0.25
    west, south, east, north = bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad
    LOG.info("settlement query bbox S %.3f W %.3f N %.3f E %.3f", south, west, north, east)
    elements = fetch_settlements(cache, west, south, east, north)
    candidates = []
    for element in elements:
        tags = element.get("tags") or {}
        place = tags.get("place")
        if place not in {"village", "town", "city"}:
            continue
        name = settlement_name(tags)
        lonlat = element_lonlat(element)
        if not name or lonlat is None:
            continue
        lon, lat = lonlat
        if distance_to_line(portion, lon, lat) > CORRIDOR_M:
            continue
        candidates.append((element, name, lon, lat, place))
    LOG.info("settlements within 15 km of Taunsa–Kotri: %s", len(candidates))
    if not candidates:
        raise RuntimeError("no settlements within 15 km of the Indus between Taunsa and Kotri")

    prepared_flood, _flood_geom = load_flood(cache)
    flooded = []
    for item in candidates:
        _element, _name, lon, lat, _place = item
        if prepared_flood.intersects(Point(lon, lat)):
            flooded.append(item)
    LOG.info("of which inside the 2022 UNOSAT flood extent: %s", len(flooded))
    if not flooded:
        raise RuntimeError("no corridor settlements fall inside the UNOSAT flood extent")

    admin = load_admin(cache)
    points = gpd.GeoDataFrame(
        {"name": [item[1] for item in flooded]},
        geometry=[Point(item[2], item[3]) for item in flooded],
        crs=4326,
    )
    districts = assign_districts(points, admin)

    worldpop_path = cache / "pak_ppp_2020.tif"
    rows = []
    used_ids: dict[str, int] = {}
    with rasterio.open(worldpop_path) as dataset:
        LOG.info("WorldPop %s %s nodata=%s", dataset.crs, dataset.shape, dataset.nodata)
        for index, (element, name, lon, lat, place) in enumerate(flooded):
            river_km, bank, _distance = project_onto(line_m, kilometres, lon, lat)
            population = population_within_1km(dataset, lon, lat)
            district = districts[index]
            base = slug(district) + "-" + slug(name)
            if not slug(name):
                base = slug(district) + f"-osm-{element['id']}"
            if not base.strip("-"):
                base = f"osm-{element['id']}"
            used_ids[base] = used_ids.get(base, 0) + 1
            village_id = base if used_ids[base] == 1 else f"{base}-{used_ids[base]}"
            osm_name = (element.get("tags") or {}).get("name") or name
            rows.append(
                {
                    "id": village_id,
                    "name": name,
                    "district": district,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "river_km": round(river_km, 3),
                    "bank": bank,
                    "population": population,
                    "population_source": POPULATION_SOURCE,
                    "sources": [
                        f"OpenStreetMap {element['type']} {element['id']} place={place} name={osm_name} (ODbL)",
                        FLOOD_SOURCE,
                        WORLDPOP_SOURCE,
                        ADMIN_SOURCE,
                        RIVER_SOURCE,
                    ],
                }
            )
            if (index + 1) % 250 == 0:
                LOG.info("population summed for %s / %s", index + 1, len(flooded))
    rows.sort(key=lambda row: (row["river_km"], row["id"]))
    # Reassign duplicate ids after the sort so the numeric suffix is stable.
    seen: dict[str, int] = {}
    for row in rows:
        base = row["id"]
        # ids may already have a suffix from the first pass; rebuild from district and name
        base = slug(row["district"]) + "-" + slug(row["name"])
        if not slug(row["name"]):
            base = row["id"]
        seen[base] = seen.get(base, 0) + 1
        row["id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    VILLAGES_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("wrote %s (%s settlements)", VILLAGES_PATH, len(rows))
    return rows


def check() -> None:
    """Validate the published files. Raises SystemExit on failure."""
    errors: list[str] = []
    payload = json.loads(INDUS_PATH.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    if payload.get("type") != "FeatureCollection" or len(features) != 1:
        errors.append("indus.geojson must be a FeatureCollection with one feature")
    else:
        feature = features[0]
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        coords = geometry.get("coordinates") or []
        if geometry.get("type") != "LineString":
            errors.append("indus geometry must be a LineString")
        if not (250 <= len(coords) <= 360):
            errors.append(f"vertex count {len(coords)} is not about 300")
        if props.get("river_km_start") != 0:
            errors.append("river_km_start must be 0")
        river_km = props.get("river_km") or []
        if len(river_km) != len(coords):
            errors.append("river_km length must match coordinates")
        elif any(river_km[i] > river_km[i + 1] + 1e-6 for i in range(len(river_km) - 1)):
            errors.append("river_km must be non-decreasing from Tarbela")
        elif abs(river_km[0]) > 1e-6:
            errors.append("river_km must start at 0")
        line = shape(geometry)
        line_m = _projected(line)
        report = anchor_report(line_m)
        by_name = {name: (distance, along) for name, distance, along in report}
        for name, limit in (("Tarbela", 2000), ("Taunsa", 3000), ("Kotri", 2000)):
            if by_name[name][0] > limit:
                errors.append(f"{name} is {by_name[name][0]:.0f} m from the centreline")
        along = [by_name[name][1] for name, _anchor in ANCHORS]
        if along != sorted(along):
            errors.append(f"barrage order along the line is wrong: {along}")
        if not (1100 <= (props.get("river_km_end") or 0) <= 2000):
            errors.append(f"river length {props.get('river_km_end')} km is outside 1100–2000")
        portion = taunsa_kotri_portion(line_m)
        villages = json.loads(VILLAGES_PATH.read_text(encoding="utf-8"))
        if not isinstance(villages, list) or not villages:
            errors.append("villages.json must be a non-empty list")
        else:
            required = {
                "id",
                "name",
                "district",
                "lat",
                "lon",
                "river_km",
                "bank",
                "population",
                "population_source",
                "sources",
            }
            ids = set()
            far = 0
            for row in villages:
                missing = required - set(row)
                if missing:
                    errors.append(f"{row.get('id')} missing {sorted(missing)}")
                    break
                if row["id"] in ids:
                    errors.append(f"duplicate id {row['id']}")
                ids.add(row["id"])
                if row["population_source"] != POPULATION_SOURCE:
                    errors.append(f"{row['id']} population_source {row['population_source']!r}")
                    break
                if row["bank"] not in {"left", "right"}:
                    errors.append(f"{row['id']} bank {row['bank']!r}")
                    break
                if not isinstance(row["sources"], list) or not row["sources"]:
                    errors.append(f"{row['id']} needs a non-empty sources list")
                    break
                if not isinstance(row["population"], int) or row["population"] < 0:
                    errors.append(f"{row['id']} population must be a non-negative integer")
                    break
                if distance_to_line(portion, row["lon"], row["lat"]) > CORRIDOR_M + 100:
                    far += 1
            if far:
                errors.append(f"{far} villages are more than 15 km from the Taunsa–Kotri centreline")
            LOG.info("villages %s, unique ids %s", len(villages), len(ids))
    if errors:
        for error in errors:
            LOG.error("%s", error)
        raise SystemExit(1)
    LOG.info("check passed")


def build(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    download(FLOOD_URL, cache / "viirs_flood.zip", minimum_bytes=100_000)
    download(ADMIN_URL, cache / "pak_admin_boundaries.shp.zip", minimum_bytes=1_000_000)
    download(WORLDPOP_URL, cache / "pak_ppp_2020.tif", minimum_bytes=500_000_000)
    elements = fetch_indus_ways(cache)
    raw = build_raw_centreline(elements)
    cut = cut_tarbela_to_kotri(raw)
    simplified = simplify_to_about(cut)
    anchor_report(simplified)
    published = _geographic(simplified)
    write_indus(published)
    build_village_rows(cache)
    check()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Indus centreline and floodplain villages.")
    parser.add_argument("--check", action="store_true", help="validate the published JSON files and exit")
    parser.add_argument("--cache", type=Path, default=None, help="download cache directory")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    if args.check:
        check()
        return
    build(args.cache or default_cache())


if __name__ == "__main__":
    main()
