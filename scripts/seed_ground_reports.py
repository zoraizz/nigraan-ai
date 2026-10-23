"""Refill Ground Photo Intake after a Render restart.

Render's free tier disk is ephemeral: a restart wipes the JSON store and the
JPEGs under it, so the demo comes back empty. This script posts a folder of
photos to POST /intake on a running damage-checker. It does not call the
vision model and it does not read GEMINI_API_KEY. The service does that work.
Photos stay outside the repo. Do not commit them.

Usage note
----------
A useful demo set is about 12 photos across 4 districts (Dadu, Khairpur,
Sukkur, Larkana), including one duplicate pair and one rooftop rescue. Post
the pair in order so the second photo folds onto the first (duplicate_of is
printed when the service sets it). The rooftop rescue is the photo where
people are on a roof: the service marks that urgent. Counts on
GET /ground-summary are shares over unique non-rejected reports; this script
only posts, it does not score.

From the repo root, with damage-checker listening (local default port 8001):

    python scripts/seed_ground_reports.py --folder D:\\demo\\ground-photos --mapping D:\\demo\\ground-photos.csv --summary

    python scripts/seed_ground_reports.py --base-url https://<damage-checker>.onrender.com --folder D:\\demo\\ground-photos

Each POST waits up to 120 seconds. The first call after a cold start is the
slow one; later calls are the model, not the boot.

Mapping CSV
-----------
Optional. Header required, columns in any order:

    filename, district, village, lat, lon, reporter_role

filename is the path relative to --folder, or a unique file name in that
folder. Leave lat and lon blank when the photo has no coordinates. An empty
reporter_role is omitted and the service stores citizen. The same filename
may appear on two rows: that is one way to seed the duplicate pair. Images
in the folder that the CSV does not name are still posted, after the CSV
rows, with no location query. Rows are sent in file order so the duplicate
pair and the rooftop rescue land in the order you listed them.

reporter_role is field_worker, rescue_team, or citizen. district should be
one of the 16 names the service already knows; the service trims it and
keeps the text either way.

Example (three of the twelve; the rest of the folder follows the same shape):

    filename,district,village,lat,lon,reporter_role
    dadu-street.jpg,Dadu,Johi,,,field_worker
    dadu-street-copy.jpg,Dadu,Johi,,,field_worker
    khairpur-rooftop.jpg,Khairpur,,,,rescue_team

Printed line
------------
One line per photo, on stdout:

    filename -> route, urgent, district

route is ground, satellite, or irrelevant. urgent is true or false on a
ground report and "-" otherwise. district is the district the service stored
(ground location, or the satellite area) and falls back to the CSV district.
A ground duplicate adds duplicate_of=<id>. An irrelevant photo adds
reason=<vlm_reason>. A failed post uses route error and a short cause.

--summary then prints the GET /ground-summary JSON. Exit status is 0 only
when every post and, if asked, the summary call succeeded.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import requests

# ---- config ----

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
# Cold start on the free tier can sit until the process is up, then the
# vision call still has to finish. One budget covers both.
TIMEOUT_SECONDS = 120
MAPPING_COLUMNS = ("filename", "district", "village", "lat", "lon", "reporter_role")
IMAGE_SUFFIXES = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
})
_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class SeedError(Exception):
    """One photo could not be posted. The message is safe to print."""


class AmbiguousFilename(SeedError):
    """More than one image in the folder matches this CSV filename."""

    def __init__(self, filename: str, matches: list[Path]) -> None:
        super().__init__(
            f"{filename} matches {len(matches)} files; use a relative path"
        )
        self.matches = matches


# ---- mapping ----

def load_mapping(path: Path) -> list[dict[str, str]]:
    """Read the mapping CSV. Raises SeedError if the header is incomplete."""
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise SeedError(f"could not read mapping CSV: {exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SeedError("mapping CSV has no header row.")
        fields = [(name or "").strip().lower() for name in reader.fieldnames]
        missing = [column for column in MAPPING_COLUMNS if column not in fields]
        if missing:
            raise SeedError(
                "mapping CSV is missing columns: " + ", ".join(missing)
            )
        rows: list[dict[str, str]] = []
        for raw in reader:
            if raw is None:
                continue
            row = {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in raw.items()
                if key is not None
            }
            if not row.get("filename"):
                continue
            rows.append(row)
    return rows


def query_from_row(row: dict[str, str] | None) -> dict[str, str]:
    """Query params for POST /intake. Empty cells are omitted.

    lat and lon are checked as numbers here so a bad cell fails that row
    instead of becoming a 422 after the upload.
    """
    if not row:
        return {}
    params: dict[str, str] = {}
    for key in ("district", "village", "reporter_role"):
        value = row.get(key, "").strip()
        if value:
            params[key] = value
    for key in ("lat", "lon"):
        value = row.get(key, "").strip()
        if not value:
            continue
        try:
            number = float(value)
        except ValueError as exc:
            raise SeedError(f"{key} is not a number: {value}") from exc
        if key == "lat" and not -90 <= number <= 90:
            raise SeedError(f"lat is outside -90..90: {value}")
        if key == "lon" and not -180 <= number <= 180:
            raise SeedError(f"lon is outside -180..180: {value}")
        params[key] = value
    return params


# ---- images ----

def list_images(folder: Path) -> list[Path]:
    """Image files under folder, sorted by relative path. Hidden names are skipped."""
    found: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        found.append(path)
    found.sort(key=lambda item: item.relative_to(folder).as_posix().lower())
    return found


def _index_images(images: list[Path], folder: Path) -> dict[str, list[Path]]:
    """Map lower-case file name and relative path to the files that use it."""
    index: dict[str, list[Path]] = {}
    for path in images:
        relative = path.relative_to(folder).as_posix().lower()
        for key in (path.name.lower(), relative):
            bucket = index.setdefault(key, [])
            if path not in bucket:
                bucket.append(path)
    return index


def resolve_filename(index: dict[str, list[Path]], filename: str) -> Path | None:
    """Find one image for a CSV filename. None if it is not in the folder."""
    key = filename.replace("\\", "/").strip().lower()
    matches = index.get(key, [])
    if len(matches) > 1:
        raise AmbiguousFilename(filename, matches)
    if len(matches) == 1:
        return matches[0]
    return None


def plan_posts(
    folder: Path,
    rows: list[dict[str, str]] | None,
) -> list[tuple[Path | None, dict[str, str] | None, str, str | None]]:
    """(path or None, mapping row or None, label, error or None) in post order.

    CSV rows go first, including a repeated filename. Folder images the CSV
    never names follow, once each. path is None when a CSV filename is missing
    or ambiguous; the label is still the filename so the printed line matches
    the spreadsheet. Ambiguous matches are not posted again without a district.
    """
    images = list_images(folder)
    if not rows:
        return [
            (path, None, path.relative_to(folder).as_posix(), None)
            for path in images
        ]
    index = _index_images(images, folder)
    planned: list[tuple[Path | None, dict[str, str] | None, str, str | None]] = []
    seen: set[Path] = set()
    for row in rows:
        label = row["filename"]
        try:
            path = resolve_filename(index, label)
        except AmbiguousFilename as exc:
            planned.append((None, row, label, str(exc)))
            seen.update(exc.matches)
            continue
        if path is None:
            planned.append((None, row, label, "missing file"))
            continue
        planned.append((path, row, label, None))
        seen.add(path)
    for path in images:
        if path not in seen:
            planned.append((path, None, path.relative_to(folder).as_posix(), None))
    return planned


# ---- intake ----

def _dash(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return text or "-"


def format_line(
    filename: str,
    route: str,
    urgent: str,
    district: str,
    extra: list[str] | None = None,
) -> str:
    """filename -> route, urgent, district, plus any extra notes."""
    parts = [route, urgent, district, *(extra or [])]
    return f"{filename} -> {', '.join(parts)}"


def fields_from_body(
    body: dict,
    sent: dict[str, str],
) -> tuple[str, str, str, list[str]]:
    """route, urgent, district, extra notes from one /intake JSON body."""
    route = str(body.get("route") or "error")
    extra: list[str] = []
    sent_district = sent.get("district") or ""
    if route == "ground":
        report = body.get("report") if isinstance(body.get("report"), dict) else {}
        urgent_raw = report.get("urgent")
        if urgent_raw is True:
            urgent = "true"
        elif urgent_raw is False:
            urgent = "false"
        else:
            urgent = "-"
        location = report.get("location") if isinstance(report.get("location"), dict) else {}
        district = _dash(location.get("district") or sent_district)
        duplicate_of = report.get("duplicate_of")
        if duplicate_of:
            extra.append(f"duplicate_of={duplicate_of}")
        return route, urgent, district, extra
    if route == "satellite":
        satellite = body.get("satellite") if isinstance(body.get("satellite"), dict) else {}
        return route, "-", _dash(satellite.get("area") or sent_district), extra
    if route == "irrelevant":
        reason = body.get("reason")
        if reason:
            extra.append(f"reason={reason}")
        return route, "-", _dash(sent_district), extra
    code = body.get("code")
    if code:
        extra.append(f"code={code}")
    message = body.get("error")
    if isinstance(message, str) and message.strip():
        extra.append(message.strip())
    return "error", "-", _dash(sent_district), extra


def post_image(
    session: requests.Session,
    base_url: str,
    path: Path,
    params: dict[str, str],
) -> requests.Response:
    """POST one image to /intake. The file is streamed, not loaded twice."""
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    with path.open("rb") as handle:
        return session.post(
            f"{base_url}/intake",
            params=params,
            files={"image": (path.name, handle, mime)},
            timeout=TIMEOUT_SECONDS,
        )


def intake_line(
    session: requests.Session,
    base_url: str,
    path: Path | None,
    row: dict[str, str] | None,
    label: str,
    problem: str | None = None,
) -> tuple[str, bool]:
    """Post one planned row. Returns the stdout line and whether it succeeded."""
    if path is None:
        return format_line(
            label, "error", "-", _dash((row or {}).get("district")),
            [problem or "missing file"],
        ), False
    try:
        params = query_from_row(row)
    except SeedError as exc:
        return format_line(label, "error", "-", _dash((row or {}).get("district")), [str(exc)]), False
    try:
        response = post_image(session, base_url, path, params)
    except requests.Timeout:
        return format_line(label, "error", "-", _dash(params.get("district")), ["timeout"]), False
    except requests.RequestException as exc:
        return format_line(
            label, "error", "-", _dash(params.get("district")),
            [f"request failed: {exc.__class__.__name__}"],
        ), False
    try:
        body = response.json()
    except ValueError:
        return format_line(
            label, "error", "-", _dash(params.get("district")),
            [f"HTTP {response.status_code}, response was not JSON"],
        ), False
    if not isinstance(body, dict):
        return format_line(
            label, "error", "-", _dash(params.get("district")),
            [f"HTTP {response.status_code}, response was not an object"],
        ), False
    route, urgent, district, extra = fields_from_body(body, params)
    if response.status_code >= 400 or route == "error":
        if response.status_code >= 400 and not any(note.startswith("HTTP ") for note in extra):
            extra = [f"HTTP {response.status_code}", *extra]
        return format_line(label, "error", "-", district, extra), False
    return format_line(label, route, urgent, district, extra), True


# ---- summary ----

def fetch_summary(session: requests.Session, base_url: str) -> dict:
    """GET /ground-summary. Raises SeedError with a short, key-free message."""
    try:
        response = session.get(f"{base_url}/ground-summary", timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise SeedError("GET /ground-summary timed out") from exc
    except requests.RequestException as exc:
        raise SeedError(f"GET /ground-summary failed: {exc.__class__.__name__}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise SeedError(
            f"GET /ground-summary returned HTTP {response.status_code}, not JSON"
        ) from exc
    if response.status_code >= 400 or not isinstance(body, dict):
        raise SeedError(f"GET /ground-summary returned HTTP {response.status_code}")
    return body


def print_summary(body: dict) -> None:
    print("GET /ground-summary")
    print(json.dumps(body, indent=2, ensure_ascii=False))


# ---- cli ----

def _base_url(value: str) -> str:
    text = value.strip().rstrip("/")
    if not text:
        raise argparse.ArgumentTypeError("base URL is empty")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Post a folder of ground photos to damage-checker POST /intake "
            "so a wiped Render disk is not an empty demo."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        type=_base_url,
        help=f"damage-checker base URL (default {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--folder",
        required=True,
        type=Path,
        help="folder of images to post (photos are not stored in the repo)",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=None,
        help="CSV columns: filename, district, village, lat, lon, reporter_role",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="after posting, print GET /ground-summary",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    folder: Path = args.folder
    if not folder.is_dir():
        print(f"folder not found: {folder}", file=sys.stderr)
        return 1
    try:
        rows = load_mapping(args.mapping) if args.mapping else None
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    posts = plan_posts(folder, rows)
    if not posts:
        print(f"no images in {folder}", file=sys.stderr)
        return 1

    failed = 0
    with requests.Session() as session:
        for path, row, label, problem in posts:
            line, ok = intake_line(session, args.base_url, path, row, label, problem)
            print(line)
            if not ok:
                failed += 1
        if failed:
            print(f"posted {len(posts) - failed}, failed {failed}", file=sys.stderr)
        if args.summary:
            try:
                print_summary(fetch_summary(session, args.base_url))
            except SeedError as exc:
                print(str(exc), file=sys.stderr)
                return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
