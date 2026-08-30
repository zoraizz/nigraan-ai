"""
xBD Dataset Preparation Script for Nigraan AI Damage Checker.

Downloads (or picks up manually-downloaded) xBD data, filters for flood-
related disaster events, remaps the 4-class xBD labels to our 3-class
API contract (none | partial | destroyed), and outputs in the folder
layout DamageDataset expects.

Usage:
    # If xBD data is already downloaded/extracted:
    python prepare_xbd_data.py --xbd_root ./xbd_raw --output_dir ./data/xbd

    # To see download instructions:
    python prepare_xbd_data.py --show_download_instructions

See the "MANUAL DOWNLOAD STEPS" section below if automated download is
not possible (xView2.org typically requires browser-based account auth).
"""

import argparse
import csv
import json
import os
import random
import shutil
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

# ============================================================================
# LABEL REMAPPING — xBD 4-class → Nigraan 3-class
# ============================================================================
#
# xBD labels:        Our labels (API_CONTRACT.md):
#   no-damage    →     none
#   minor-damage →     partial
#   major-damage →     destroyed  ← DECISION (see rationale below)
#   destroyed    →     destroyed
#
# RESOLVED DECISION — major-damage → destroyed (not partial):
#   Rationale: In our aid-priority use case, "major-damage" is closer to
#   "needs urgent aid" than "needs minor aid." Grouping it with "destroyed"
#   better serves downstream triage — it's safer to over-flag a severely
#   damaged building for immediate attention than to under-flag it as only
#   "partial." This trades precision for recall on the high-severity class,
#   which is the right tradeoff for disaster response.
#
XBD_TO_NIGRAAN = {
    "no-damage":    "none",
    "minor-damage": "partial",
    "major-damage": "destroyed",  # ← DECISION: see rationale above
    "destroyed":    "destroyed",
}

# xBD damage scale integer → string (used in some label formats)
XBD_DAMAGE_SCALE = {
    0: "no-damage",
    1: "minor-damage",
    2: "major-damage",
    3: "destroyed",
}

# ============================================================================
# Flood-related disaster events in xBD
# ============================================================================
# xBD disaster names that involve flooding. Used to filter the subset.
# Source: xBD metadata / event listings. Add more if new events are relevant.
FLOOD_DISASTER_KEYWORDS = [
    "flood",
    "hurricane",   # hurricanes cause major flooding
    "typhoon",     # typhoons cause major flooding
    "tsunami",
    "cyclone",
]


def is_flood_related(disaster_name: str) -> bool:
    """Check if a disaster event name is flood-related."""
    name_lower = disaster_name.lower().replace("-", " ").replace("_", " ")
    return any(kw in name_lower for kw in FLOOD_DISASTER_KEYWORDS)


# ============================================================================
# xBD Label Parsing
# ============================================================================

def parse_xbd_label_file(label_path: Path) -> list[dict]:
    """Parse an xBD JSON label file and extract per-building damage labels.

    xBD label JSON structure (post-disaster):
    {
        "features": {
            "xy": [
                {
                    "properties": {
                        "subtype": "no-damage" | "minor-damage" | ...
                        "feature_type": "building"
                    },
                    "wkt": "POLYGON(...)"
                },
                ...
            ]
        },
        "metadata": {
            "disaster": "hurricane-harvey",
            "disaster_type": "hurricane",
            ...
        }
    }

    Returns a list of dicts with keys: disaster, damage_label (xBD original).
    """
    with open(label_path, "r") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    disaster = metadata.get("disaster", "unknown")

    buildings = []
    features = data.get("features", {}).get("xy", [])
    for feat in features:
        props = feat.get("properties", {})
        if props.get("feature_type") != "building":
            continue
        subtype = props.get("subtype", "unclassified")
        if subtype == "unclassified" or subtype not in XBD_TO_NIGRAAN:
            continue
        buildings.append({
            "disaster": disaster,
            "damage_xbd": subtype,
            "damage_nigraan": XBD_TO_NIGRAAN[subtype],
        })

    return buildings


def get_majority_label(buildings: list[dict]) -> Optional[str]:
    """Determine the majority damage label for an image tile.

    xBD labels are per-building (polygon), but our model classifies entire
    image tiles. We take the *worst* (highest severity) label present in
    the tile as the tile-level label, which is the standard approach in
    xBD literature for tile-level classification.

    Severity order: none < partial < destroyed.
    """
    if not buildings:
        return None

    severity_order = {"none": 0, "partial": 1, "destroyed": 2}
    worst = max(buildings, key=lambda b: severity_order.get(b["damage_nigraan"], 0))
    return worst["damage_nigraan"]


# ============================================================================
# Main Preparation Logic
# ============================================================================

def find_xbd_post_images(xbd_root: Path) -> list[dict]:
    """Scan xBD directory tree for post-disaster image + label pairs.

    xBD layout (typical after extraction):
        xbd_root/
            train/ (or tier1/, tier3/, etc.)
                images/
                    {disaster}_{id}_post_disaster.png
                    {disaster}_{id}_pre_disaster.png
                labels/
                    {disaster}_{id}_post_disaster.json
                    {disaster}_{id}_pre_disaster.json

    Returns list of dicts with: image_path, label_path, disaster, tile_id.
    """
    pairs = []

    # Search recursively for post-disaster images
    for img_path in xbd_root.rglob("*_post_disaster.png"):
        # Derive label path
        label_name = img_path.stem + ".json"
        # Labels might be in a sibling "labels" dir or same dir
        label_candidates = [
            img_path.parent.parent / "labels" / label_name,
            img_path.parent / label_name,
            img_path.with_suffix(".json"),
        ]
        label_path = None
        for candidate in label_candidates:
            if candidate.exists():
                label_path = candidate
                break

        if label_path is None:
            continue

        # Extract disaster name and tile ID from filename
        # Format: {disaster}_{id}_post_disaster.png
        stem = img_path.stem.replace("_post_disaster", "")
        parts = stem.rsplit("_", 1)
        if len(parts) == 2:
            disaster_name, tile_id = parts
        else:
            disaster_name = "unknown"
            tile_id = stem

        pairs.append({
            "image_path": img_path,
            "label_path": label_path,
            "disaster": disaster_name,
            "tile_id": tile_id,
            "full_id": stem,
        })

    return pairs


def prepare_subset(
    xbd_root: str,
    output_dir: str,
    max_samples: int = 150,
    flood_only: bool = True,
    seed: int = 42,
) -> dict:
    """Filter, remap, and export an xBD subset to DamageDataset format.

    Args:
        xbd_root:    Path to extracted xBD data.
        output_dir:  Output directory (will contain images/ + labels.csv).
        max_samples: Maximum number of image tiles to include.
        flood_only:  If True, only include flood-related disasters.
        seed:        Random seed for reproducible sampling.

    Returns:
        Dict with statistics about the prepared subset.
    """
    xbd_path = Path(xbd_root)
    out_path = Path(output_dir)
    out_images = out_path / "images"
    out_images.mkdir(parents=True, exist_ok=True)

    print(f"[prepare_xbd] Scanning {xbd_path} for post-disaster tiles...")
    all_pairs = find_xbd_post_images(xbd_path)
    print(f"[prepare_xbd] Found {len(all_pairs)} post-disaster image+label pairs")

    if not all_pairs:
        print("[prepare_xbd] ERROR: No xBD data found. Check --xbd_root path.")
        print("[prepare_xbd] Expected layout: xbd_root/**/images/*_post_disaster.png")
        sys.exit(1)

    # Filter for flood-related disasters
    if flood_only:
        flood_pairs = [p for p in all_pairs if is_flood_related(p["disaster"])]
        print(f"[prepare_xbd] Flood-related tiles: {len(flood_pairs)}")
        if not flood_pairs:
            print("[prepare_xbd] WARNING: No flood-related tiles found. "
                  "Falling back to all disasters.")
            flood_pairs = all_pairs
    else:
        flood_pairs = all_pairs

    # Parse labels and assign tile-level damage
    labeled_tiles = []
    for pair in flood_pairs:
        buildings = parse_xbd_label_file(pair["label_path"])
        tile_label = get_majority_label(buildings)
        if tile_label is None:
            # Skip tiles with no labeled buildings
            continue
        pair["label"] = tile_label
        pair["num_buildings"] = len(buildings)
        labeled_tiles.append(pair)

    print(f"[prepare_xbd] Tiles with labeled buildings: {len(labeled_tiles)}")

    # Stratified sampling: try to balance classes
    random.seed(seed)
    by_class = {"none": [], "partial": [], "destroyed": []}
    for tile in labeled_tiles:
        by_class[tile["label"]].append(tile)

    print("[prepare_xbd] Class distribution (before sampling):")
    for cls, tiles in by_class.items():
        print(f"  {cls}: {len(tiles)}")

    # Sample up to max_samples, balanced across classes
    per_class = max_samples // 3
    sampled = []
    for cls in ["none", "partial", "destroyed"]:
        pool = by_class[cls]
        random.shuffle(pool)
        n = min(per_class, len(pool))
        sampled.extend(pool[:n])

    # If we have room, fill remaining from any class
    remaining = max_samples - len(sampled)
    if remaining > 0:
        unsampled = [t for t in labeled_tiles if t not in sampled]
        random.shuffle(unsampled)
        sampled.extend(unsampled[:remaining])

    random.shuffle(sampled)
    print(f"[prepare_xbd] Final subset: {len(sampled)} tiles")

    # Copy images and write labels.csv
    labels_path = out_path / "labels.csv"
    stats = {"none": 0, "partial": 0, "destroyed": 0}

    with open(labels_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label"])

        for i, tile in enumerate(sampled):
            img_id = f"{i:04d}"
            src = tile["image_path"]
            dst = out_images / f"{img_id}.png"

            # Copy (or resize if needed — xBD tiles are 1024x1024)
            img = Image.open(src).convert("RGB")
            # Keep original resolution; DamageDataset transforms handle resizing
            img.save(dst)

            writer.writerow([img_id, tile["label"]])
            stats[tile["label"]] += 1

    print(f"\n[prepare_xbd] Prepared {len(sampled)} tiles -> {out_path}")
    print(f"[prepare_xbd] Class distribution:")
    for cls, count in stats.items():
        print(f"  {cls}: {count}")
    print(f"[prepare_xbd] Labels written to {labels_path}")

    # Write a manifest for traceability
    manifest_path = out_path / "manifest.json"
    manifest = {
        "source": "xBD (xView2)",
        "flood_only": flood_only,
        "total_tiles": len(sampled),
        "class_distribution": stats,
        "label_remapping": XBD_TO_NIGRAAN,
        "label_remapping_note": (
            "major-damage mapped to 'destroyed' (not 'partial'). "
            "Rationale: major-damage is closer to 'needs urgent aid' — "
            "grouping with destroyed better serves aid-priority triage. "
            "See prepare_xbd_data.py for full rationale."
        ),
        "tile_level_labeling": "worst (highest severity) building label per tile",
        "disasters_included": list(set(t["disaster"] for t in sampled)),
        "tiles": [
            {
                "output_id": f"{i:04d}",
                "original_id": t["full_id"],
                "disaster": t["disaster"],
                "label_xbd_majority": t["label"],
                "num_buildings": t["num_buildings"],
            }
            for i, t in enumerate(sampled)
        ],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[prepare_xbd] Manifest written to {manifest_path}")

    return stats


# ============================================================================
# Download Instructions
# ============================================================================

DOWNLOAD_INSTRUCTIONS = """
================================================================================
 xBD DATASET — MANUAL DOWNLOAD INSTRUCTIONS
================================================================================

The xBD dataset requires an approved xView2 account. Automated download is
not supported because the site requires browser-based authentication.

STEPS:

1. Go to https://xview2.org/dataset
2. Log in with your approved account credentials.
3. Download ONE of these (smallest first):
   - "Train" split (recommended for first pass, ~7 GB compressed)
   - Or: "Tier 1" if the site offers tiered downloads
4. Extract the downloaded archive(s) into:
       damage-checker/xbd_raw/
   After extraction you should see something like:
       xbd_raw/
           train/
               images/
                   hurricane-harvey_00000000_post_disaster.png
                   hurricane-harvey_00000000_pre_disaster.png
                   ...
               labels/
                   hurricane-harvey_00000000_post_disaster.json
                   hurricane-harvey_00000000_pre_disaster.json
                   ...

5. Then run this script:
       python prepare_xbd_data.py --xbd_root ./xbd_raw --output_dir ./data/xbd

   This will:
   - Filter for flood/hurricane/typhoon events (~50-200 tiles)
   - Remap xBD 4-class labels to our 3-class scheme
   - Output to data/xbd/ in DamageDataset-compatible format

6. Train on the real data:
       python train.py --data_dir ./data/xbd --epochs 15 --checkpoint_dir ./checkpoints --checkpoint_name xbd_real_model.pth

NOTES:
- xbd_raw/ is gitignored, so the raw download won't be committed.
- data/xbd/ is also gitignored (under data/).
- Only scripts and result summaries are committed.
================================================================================
"""


def main():
    parser = argparse.ArgumentParser(
        description="Prepare xBD data for Nigraan AI damage checker"
    )
    parser.add_argument(
        "--xbd_root", type=str, default="./xbd_raw",
        help="Path to extracted xBD dataset root"
    )
    parser.add_argument(
        "--output_dir", type=str, default="./data/xbd",
        help="Output directory for prepared subset"
    )
    parser.add_argument(
        "--max_samples", type=int, default=150,
        help="Maximum number of tiles to include (default: 150)"
    )
    parser.add_argument(
        "--all_disasters", action="store_true",
        help="Include all disaster types, not just flood-related"
    )
    parser.add_argument(
        "--show_download_instructions", action="store_true",
        help="Print download instructions and exit"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible sampling"
    )
    args = parser.parse_args()

    if args.show_download_instructions:
        print(DOWNLOAD_INSTRUCTIONS)
        return

    xbd_root = Path(args.xbd_root)
    if not xbd_root.exists():
        print(f"[prepare_xbd] ERROR: xBD root not found at {xbd_root}")
        print("[prepare_xbd] Run with --show_download_instructions for setup steps.")
        sys.exit(1)

    stats = prepare_subset(
        xbd_root=args.xbd_root,
        output_dir=args.output_dir,
        max_samples=args.max_samples,
        flood_only=not args.all_disasters,
        seed=args.seed,
    )

    print("\n[prepare_xbd] Done! Next step:")
    print(f"  python train.py --data_dir {args.output_dir} --epochs 15 "
          f"--checkpoint_dir ./checkpoints --checkpoint_name xbd_real_model.pth")


if __name__ == "__main__":
    main()
