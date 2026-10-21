"""Build flood-tracker/data/flows_2022.csv from FFC Daily Flood Situation Reports.

Annexure-I of each DFSR is the 06:00 (Asia/Karachi) river table. For the Indus
block the columns are: designed capacity, historic peak discharge, date of that
peak, last year's inflow, last year's outflow, today's inflow, today's outflow,
flood classification with trend (R rising, F falling, S stable), then the
comparative Very High danger level. Today's pair is the last two discharge
tokens before the category. Classification is applied to outflow.

PDFs are cached under scripts/flood/raw/ and are not committed. A day whose PDF
is not published is logged. A gap is filled only when a named news article
states the clock time and both discharges; those rows keep that article as
source_url. No missing day is interpolated.

--verify checks nine published outflow checkpoints and exits non-zero if any
is off by more than 2 percent. Four further news figures are printed beside
the parsed values and do not affect the exit code.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path(__file__).resolve().parent / "raw"
CSV_PATH = ROOT / "flood-tracker" / "data" / "flows_2022.csv"

START = date(2022, 8, 10)
END = date(2022, 9, 20)

BARRAGES = ("Tarbela", "Kalabagh", "Chashma", "Taunsa", "Guddu", "Sukkur", "Kotri")

# Longest forms first so "Very High" is not read as "High".
CATEGORY_RE = re.compile(
    r"("
    r"Exceptionally\s+High\s+Flood"
    r"|Ex\.?\s*High\s+Flood"
    r"|EHF"
    r"|Very\s+High\s+Flood"
    r"|V\.?\s*High\s+Flood"
    r"|VHF"
    r"|Medium\s+Flood"
    r"|Med\.?\s*Flood"
    r"|High\s+Flood"
    r"|Low\s+Flood"
    r"|Normal(?:\s+Flow(?:\s+Condition)?)?"
    r")",
    re.IGNORECASE,
)

CHECKPOINTS = (
    ("2022-08-29T06:00", "Kalabagh", 407000),
    ("2022-08-29T06:00", "Chashma", 519000),
    ("2022-08-29T06:00", "Taunsa", 567000),
    ("2022-08-29T06:00", "Guddu", 501000),
    ("2022-08-29T06:00", "Sukkur", 531000),
    ("2022-08-29T06:00", "Kotri", 337000),
    ("2022-09-08T06:00", "Kotri", 584000),
    ("2022-09-08T06:00", "Guddu", 186000),
    ("2022-09-08T06:00", "Sukkur", 273000),
)

# Printed for comparison only. Not checkpoints.
NEWS_COMPARE = (
    ("2022-08-30T06:00", "Taunsa", 622095),
    ("2022-09-02T12:00", "Guddu", 558218),
    ("2022-08-23T18:00", "Guddu", 576075),
    ("2022-08-25T06:00", "Sukkur", 579753),
)

# Dawn, 11 Sep 2022, Mohammad Hussain Khan, "New peak of high flood hits Kotri
# Barrage" (https://www.dawn.com/news/1709397). The FFC PDFs for 9 and 10 Sep
# return 404. The article quotes the FFD discharge report:
#   6am Saturday 10 Sep: inflow 626,053, downstream 600,018, "high flood".
#   6pm 9 Sep: "steady at 604,087 cusecs up and 583,882 cusecs downstream".
# Sukkur 185,010 and Guddu 165,161 / 158,537 are in the same piece but with no
# clock time, so they are not written.
DAWN_KOTRI = "https://www.dawn.com/news/1709397"
NEWS_GAP_FILLS = (
    {
        "date_time": "2022-09-09T18:00",
        "barrage": "Kotri",
        "inflow_cusecs": 604087,
        "outflow_cusecs": 583882,
        "ffc_category": "High Flood",
        "trend": "S",
        "source_url": DAWN_KOTRI,
    },
    {
        "date_time": "2022-09-10T06:00",
        "barrage": "Kotri",
        "inflow_cusecs": 626053,
        "outflow_cusecs": 600018,
        "ffc_category": "High Flood",
        "trend": "",
        "source_url": DAWN_KOTRI,
    },
)

COLUMNS = (
    "date_time",
    "barrage",
    "inflow_cusecs",
    "outflow_cusecs",
    "ffc_category",
    "trend",
    "source_url",
)


def pdf_name(day: date, padded: bool) -> str:
    if padded:
        return f"DFSR-{day.day:02d}-{day.month:02d}-{day.year}.pdf"
    return f"DFSR-{day.day}-{day.month}-{day.year}.pdf"


def candidate_urls(day: date) -> list[str]:
    """Canonical path first, then upload-month and unpadded WordPress names.

    FFC files sometimes land in the month they were uploaded rather than the
    report month, and the slug sometimes drops leading zeros (DFSR-1-9-2022).
    """
    folders = [f"{day.month:02d}"]
    if day.month == 9:
        folders.append("10")
    names = [pdf_name(day, True)]
    unpadded = pdf_name(day, False)
    if unpadded not in names:
        names.append(unpadded)
    # Mixed padding: DFSR-9-09-2022 and DFSR-09-9-2022.
    mixed = [
        f"DFSR-{day.day}-{day.month:02d}-{day.year}.pdf",
        f"DFSR-{day.day:02d}-{day.month}-{day.year}.pdf",
    ]
    for name in mixed:
        if name not in names:
            names.append(name)
    urls = []
    for folder in folders:
        for name in names:
            url = f"https://ffc.gov.pk/wp-content/uploads/{day.year}/{folder}/{name}"
            if url not in urls:
                urls.append(url)
    return urls


def pdf_url(day: date) -> str:
    return candidate_urls(day)[0]


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def normalize(text: str) -> str:
    return (
        text.replace("\u00a0", " ")
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\uf0b7", " ")
    )


def download(day: date) -> tuple[Path, str] | None:
    """Return (cached PDF path, source URL), or None if every candidate 404s."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / pdf_name(day, True)
    urls = candidate_urls(day)
    if dest.exists() and dest.stat().st_size > 1000 and dest.read_bytes()[:4] == b"%PDF":
        return dest, urls[0]
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "NigraanFloodTracker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError:
            continue
        except urllib.error.URLError:
            continue
        if data[:4] != b"%PDF":
            continue
        dest.write_bytes(data)
        if url != urls[0]:
            print(f"FOUND PDF {day.isoformat()} at alternate url {url}")
        return dest, url
    print(
        f"MISSING PDF {day.isoformat()} not at {urls[0]} "
        f"nor under /2022/10/ or unpadded names such as {pdf_name(day, False)}"
    )
    return None


def page_text(path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(path) as doc:
        for page in doc.pages:
            parts.append(page.extract_text() or "")
    return normalize("\n".join(parts))


def indus_block(text: str) -> str:
    """The Indus rows of the Annexure-I flow table, not the narrative.

    The bulletin mentions Annexure-I and the river names in prose before the
    table. The table itself is the section headed "River Flow Situation".
    """
    marker = None
    for found in re.finditer(r"River Flow Situation", text, re.IGNORECASE):
        marker = found
    if marker is None:
        return ""
    body = text[marker.end() :]
    match = re.search(
        r"River\s+Indus\b(.*?)(?:River\s+Kabul|River\s+Swat|River\s+Jhelum|\n\s*B\.)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else ""


def canon_category(raw: str) -> str:
    compact = re.sub(r"[.\s]+", " ", raw).strip().lower()
    if compact.startswith("exceptionally") or compact.startswith("ex high") or compact == "ehf":
        return "Exceptionally High Flood"
    if "very high" in compact or compact.startswith("v high") or compact == "vhf":
        return "Very High Flood"
    if compact.startswith("high"):
        return "High Flood"
    if compact.startswith("med"):
        return "Medium Flood"
    if compact.startswith("low"):
        return "Low Flood"
    if compact.startswith("normal"):
        return "Normal"
    raise ValueError(f"unrecognised flood category {raw!r}")


def discharge_tokens(before_category: str) -> list[int | None]:
    """Discharge tokens before the category. None means Not Received."""
    cleaned = re.sub(r"\d{1,2}-\d{1,2}-\d{2,4}", " ", before_category)
    cleaned = re.sub(r"not\s+received", " NR ", cleaned, flags=re.IGNORECASE)
    found = re.findall(r"NIL|NR|\d[\d,]*", cleaned, flags=re.IGNORECASE)
    values: list[int | None] = []
    for token in found:
        upper = token.upper()
        if upper == "NIL":
            values.append(0)
        elif upper == "NR":
            values.append(None)
        else:
            digits = token.replace(",", "")
            if digits.isdigit():
                values.append(int(digits))
    return values


def row_slice(section: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\b", section, re.IGNORECASE)
    if not match:
        return None
    rest = section[match.start() :]
    end = len(rest)
    for other in BARRAGES:
        if other.lower() == name.lower():
            continue
        later = re.search(rf"\b{other}\b", rest[1:], re.IGNORECASE)
        if later:
            end = min(end, later.start() + 1)
    return rest[:end]


def parse_row(section: str, name: str) -> dict | None:
    row = row_slice(section, name)
    if not row:
        return None
    cat = CATEGORY_RE.search(row)
    if not cat:
        return None
    tokens = discharge_tokens(row[: cat.start()])
    if len(tokens) < 2:
        return None
    inflow, outflow = tokens[-2], tokens[-1]
    if inflow is None or outflow is None:
        return None
    if inflow > 2_000_000 or outflow > 2_000_000:
        return None
    trend_match = re.search(r"\(\s*(R|F|S|NR)\s*\)", row[cat.end() : cat.end() + 24], re.IGNORECASE)
    trend = ""
    if trend_match and trend_match.group(1).upper() != "NR":
        trend = trend_match.group(1).upper()
    return {
        "barrage": name,
        "inflow_cusecs": inflow,
        "outflow_cusecs": outflow,
        "ffc_category": canon_category(cat.group(1)),
        "trend": trend,
    }


def parse_pdf(path: Path, day: date, url: str) -> list[dict]:
    text = page_text(path)
    section = indus_block(text)
    stamp = f"{day.isoformat()}T06:00"
    if not section:
        print(f"MISSING DAY {day.isoformat()} Annexure-I Indus block not found in {path.name}")
        return []
    rows = []
    for name in BARRAGES:
        parsed = parse_row(section, name)
        if not parsed:
            snippet = re.sub(r"\s+", " ", row_slice(section, name) or section[:160])
            print(f"MISSING ROW {day.isoformat()} {name} not parsed from Annexure-I | {snippet[:160]}")
            continue
        parsed["date_time"] = stamp
        parsed["source_url"] = url
        rows.append(parsed)
    return rows


def add_news_fills(rows: list[dict]) -> list[dict]:
    have = {(row["date_time"], row["barrage"]) for row in rows}
    added = []
    for fill in NEWS_GAP_FILLS:
        key = (fill["date_time"], fill["barrage"])
        if key in have:
            continue
        added.append(dict(fill))
        print(
            f"NEWS FILL {fill['date_time']} {fill['barrage']} "
            f"in {fill['inflow_cusecs']} out {fill['outflow_cusecs']} "
            f"{fill['ffc_category']} trend={fill['trend'] or 'blank'} {fill['source_url']}"
        )
    print(
        "NEWS SKIP 2022-09-10 Guddu and Sukkur: Dawn gives Saturday discharges "
        "(Guddu inflow 165161 outflow 158537, Sukkur 185010 up and downstream, Normal) "
        "but no clock time, so those rows were not written. "
        + DAWN_KOTRI
    )
    print(
        "MISSING DAYS left as gaps (no PDF, no timed news table): "
        "2022-09-12 through 2022-09-20"
    )
    return rows + added


def write_csv(rows: list[dict]) -> None:
    order = {name: index for index, name in enumerate(BARRAGES)}
    rows = sorted(rows, key=lambda row: (row["date_time"], order[row["barrage"]]))
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} rows to {CSV_PATH.relative_to(ROOT).as_posix()}")


def lookup(rows: list[dict], when: str, barrage: str) -> int | None:
    for row in rows:
        if row["date_time"] == when and row["barrage"] == barrage:
            return int(row["outflow_cusecs"])
    return None


def verify(rows: list[dict]) -> int:
    within = 0
    for when, barrage, expected in CHECKPOINTS:
        got = lookup(rows, when, barrage)
        if got is None:
            print(f"CHECKPOINT FAIL {when} {barrage} expected {expected} parsed missing")
            continue
        delta = abs(got - expected) / expected
        status = "OK" if delta <= 0.02 else "FAIL"
        if delta <= 0.02:
            within += 1
        print(
            f"CHECKPOINT {status} {when} {barrage} expected {expected} "
            f"parsed {got} off {delta * 100:.2f}%"
        )
    print(f"{within}/9 checkpoints within 2%")
    print("news comparison (not a checkpoint, does not affect exit code):")
    for when, barrage, news in NEWS_COMPARE:
        got = lookup(rows, when, barrage)
        if got is None:
            print(f"  {barrage} {when} news {news}; no parsed row at that time")
            continue
        delta = (got - news) / news
        print(f"  {barrage} {when} news {news}; parsed {got}; diff {delta * 100:+.2f}%")
    return 0 if within == 9 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse FFC DFSR Annexure-I Indus rows for Aug-Sep 2022.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="exit non-zero unless the nine outflow checkpoints are within 2%%",
    )
    args = parser.parse_args(argv)

    rows: list[dict] = []
    pdf_days = 0
    for day in daterange(START, END):
        found = download(day)
        if found is None:
            continue
        path, url = found
        pdf_days += 1
        rows.extend(parse_pdf(path, day, url))
    rows = add_news_fills(rows)
    write_csv(rows)
    print(f"PDF days parsed: {pdf_days} of {(END - START).days + 1}")
    if args.verify:
        return verify(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
