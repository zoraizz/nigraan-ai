"""JSON file store for ground reports and their photos.

The intake service keeps two things: the report documents, and the JPEG each
one was decided from. They live under GROUND_REPORTS_DIR (default
"ground_reports"):

    reports.json          a JSON list of GroundReport objects
    photos/<id>.jpg       the EXIF-free JPEG saved at intake

A relative directory is resolved from the damage-checker folder, not the
process cwd, so the same files are used whether uvicorn is started from the
repo root or from damage-checker/. An absolute path is used as given. Render's
disk is ephemeral; the variable exists so a host can point at a mounted path.

Writes are atomic: the new bytes go to a temp file in the same directory,
then os.replace swaps them into place. A crash mid-write leaves the previous
reports.json intact. The photo is written first and the index second, so a
crash between them can leave an unreferenced JPEG, never an index row whose
photo never landed. If the index write fails, the in-memory row and that new
photo are removed again.

The file is read once, at construction. Invalid JSON, or a top-level value
that is not a list, does not get replaced with an empty list: writes raise
StoreWritesPaused and the on-disk bytes stay as they were. A list that
contains a few schema-invalid objects still serves the valid rows, but writes
are paused for the same reason — the next save would drop the invalid ones.

The in-memory list is guarded by one lock that also covers the file writes.
get/list return copies, so a caller can edit a report and only the update()
call persists it.

delete removes a report and then its JPEG (a missing file is fine). Copies
that pointed at the deleted report are re-pointed in the same index write:
the oldest remaining copy becomes the group's first report and the rest
point at it.

ReportStore is the whole surface an Alibaba OSS (or any other) backend needs:
add, get, list, update, delete, photo_path, count. photo_path returns a local JPEG
path or None; an object-storage implementation can satisfy that by caching
the object into a temp file. Ids that are not 32 hex characters never become
a path, so a photo URL cannot climb out of the photos directory.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from threading import Lock
from typing import Optional, Protocol

from ground_intake.schema import GroundReport

logger = logging.getLogger(__name__)

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_REPORTS_FILE = "reports.json"
_PHOTO_DIR = "photos"
# uuid4().hex. Anything else is refused before it can touch the filesystem.
_REPORT_ID = re.compile(r"^[0-9a-fA-F]{32}$")


class StoreWritesPaused(RuntimeError):
    """reports.json could not be loaded safely, so it must not be overwritten."""


class ReportStore(Protocol):
    """The seven operations a ground-report backend has to provide."""

    def add(self, report: GroundReport, photo_jpeg: bytes) -> GroundReport: ...

    def get(self, report_id: str) -> Optional[GroundReport]: ...

    def list(self) -> list[GroundReport]: ...

    def update(self, report: GroundReport) -> GroundReport: ...

    def delete(self, report_id: str) -> None: ...

    def photo_path(self, report_id: str) -> Optional[Path]: ...

    def count(self) -> int: ...


def resolve_reports_dir(root: str | Path | None = None) -> Path:
    """Absolute reports directory.

    None reads GROUND_REPORTS_DIR, falling back to "ground_reports". A
    relative path is anchored at damage-checker/.
    """
    if root is None:
        raw = os.environ.get("GROUND_REPORTS_DIR", "").strip() or "ground_reports"
        path = Path(raw)
    else:
        path = Path(root)
    if not path.is_absolute():
        path = _SERVICE_ROOT / path
    return path.resolve()


def open_store() -> "JsonReportStore":
    """Process-wide store. The directory is fixed when this is called."""
    return JsonReportStore()


def _atomic_write(path: Path, data: bytes) -> None:
    """Write data to path via a same-directory temp file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _clone(report: GroundReport) -> GroundReport:
    return GroundReport.model_validate(report.model_dump())


# ---- JSON directory store ----


class JsonReportStore:
    """Thread-safe reports.json + photos/<id>.jpg."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = resolve_reports_dir(root)
        self._photos = self.root / _PHOTO_DIR
        self._reports_path = self.root / _REPORTS_FILE
        self._lock = Lock()
        self._reports: list[GroundReport] = []
        self._writable = True
        self._load()

    def add(self, report: GroundReport, photo_jpeg: bytes) -> GroundReport:
        """Persist a new report and its JPEG. The id must not already exist."""
        photo_file = self._photo_file(report.id)
        if photo_file is None:
            raise ValueError("report id is not a safe file name")
        with self._lock:
            self._require_writable()
            if any(item.id == report.id for item in self._reports):
                raise ValueError(f"report {report.id} already exists")
            _atomic_write(photo_file, bytes(photo_jpeg))
            self._reports.append(_clone(report))
            try:
                self._write_index()
            except Exception:
                self._reports.pop()
                try:
                    photo_file.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
        return _clone(report)

    def get(self, report_id: str) -> Optional[GroundReport]:
        with self._lock:
            found = self._find(report_id)
            return None if found is None else _clone(found)

    def list(self) -> list[GroundReport]:
        """Reports in insertion order. Each item is a copy."""
        with self._lock:
            return [_clone(report) for report in self._reports]

    def update(self, report: GroundReport) -> GroundReport:
        """Replace the stored report with this id. The JPEG is left as it was."""
        with self._lock:
            self._require_writable()
            for index, current in enumerate(self._reports):
                if current.id == report.id:
                    previous = current
                    self._reports[index] = _clone(report)
                    try:
                        self._write_index()
                    except Exception:
                        self._reports[index] = previous
                        raise
                    return _clone(report)
        raise KeyError(report.id)

    def delete(self, report_id: str) -> None:
        """Remove the report and its JPEG. Unknown ids raise KeyError.

        Copies of the deleted report are re-pointed at the oldest remaining
        copy (created_at, then insertion order), which becomes the group's
        first report. The JPEG is unlinked only after the index write lands.
        """
        with self._lock:
            self._require_writable()
            if self._find(report_id) is None:
                raise KeyError(report_id)
            previous = self._reports
            kept = [_clone(report) for report in previous if report.id != report_id]
            copies = [
                (report.created_at or "", index, report)
                for index, report in enumerate(kept)
                if report.duplicate_of == report_id
            ]
            if copies:
                _, _, head = min(copies, key=lambda item: (item[0], item[1]))
                head.duplicate_of = None
                for _, _, report in copies:
                    if report is not head:
                        report.duplicate_of = head.id
            self._reports = kept
            try:
                self._write_index()
            except Exception:
                self._reports = previous
                raise
            photo_file = self._photo_file(report_id)
            if photo_file is not None:
                try:
                    photo_file.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove photo for deleted report %s", report_id)

    def photo_path(self, report_id: str) -> Optional[Path]:
        """Local JPEG path, or None when the id is unsafe or the file is missing."""
        path = self._photo_file(report_id)
        if path is None or not path.is_file():
            return None
        resolved = path.resolve()
        if self._photos.resolve() not in resolved.parents:
            return None
        return resolved

    def count(self) -> int:
        with self._lock:
            return len(self._reports)

    def _require_writable(self) -> None:
        if not self._writable:
            raise StoreWritesPaused(
                "ground reports file could not be read; writes are paused"
            )

    def _find(self, report_id: str) -> Optional[GroundReport]:
        for report in self._reports:
            if report.id == report_id:
                return report
        return None

    def _photo_file(self, report_id: str) -> Optional[Path]:
        if not isinstance(report_id, str) or _REPORT_ID.fullmatch(report_id) is None:
            return None
        return self._photos / f"{report_id}.jpg"

    def _load(self) -> None:
        path = self._reports_path
        if not path.is_file():
            self._reports = []
            self._writable = True
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._pause(path, type(exc).__name__)
            return
        if not isinstance(payload, list):
            self._pause(path, "not-a-list")
            return
        loaded: list[GroundReport] = []
        skipped = 0
        for item in payload:
            try:
                loaded.append(GroundReport.model_validate(item))
            except Exception:
                skipped += 1
        self._reports = loaded
        if skipped:
            self._writable = False
            logger.warning(
                "Paused ground-report writes: %s entr%s in %s did not match the schema",
                skipped,
                "y" if skipped == 1 else "ies",
                path,
            )
            return
        self._writable = True

    def _pause(self, path: Path, reason: str) -> None:
        self._reports = []
        self._writable = False
        logger.warning(
            "Paused ground-report writes: could not load %s (%s)",
            path,
            reason,
        )

    def _write_index(self) -> None:
        payload = [report.model_dump(mode="json") for report in self._reports]
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        _atomic_write(self._reports_path, raw)
