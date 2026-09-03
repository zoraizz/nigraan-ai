"""
prepare_ebd_data.py — Convert EBD Pakistan Flooding dataset to damage-checker format.

Reads the raw EBD mask PNGs, applies worst-pixel heuristic (same as xBD pipeline),
maps 4-level EBD damage to our 3-class system, and outputs images + labels.csv + manifest.json.

EBD damage mask pixel values:
    0 = background
    1 = no-damage   -> "none"
    2 = minor-damage -> "partial"
    3 = major-damage -> "destroyed"
    4 = destroyed    -> "destroyed"

Usage:
    python prepare_ebd_data.py --input G:\ebd_scratch\PAKISTAN-FLOODING --output data/ebd

Actual EBD directory layout (discovered Sept 2026):
    {input}/PAKISTAN-FLOODING/images/PAKISTAN-FLOODING_{id}_post_disaster.png
    {input}/PAKISTAN-FLOODING/masks/PAKISTAN-FLOODING_{id}_post_disaster.png
    Pre-disaster masks are binary (0/255) localization only.
    Post-disaster masks carry damage levels (0=bg, 1-4 = damage scale).
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# 4-level EBD -> 3-class mapping (same rationale as xBD: major-damage ~ "needs urgent aid")
EBD_TO_3CLASS = {
    1: "none",
    2: "partial",
    3: "destroyed",
    4: "destroyed",
}


def find_ebd_root(input_path: Path) -> tuple[Path, Path]:
    """Locate the masks/ and images/ directories within the extracted EBD data.

    The ZIP extracts as: {input}/PAKISTAN-FLOODING/images/ and masks/.
    Returns (masks_dir, images_dir).
    Searches up to 3 levels deep.
    """
    # Check all directory levels for a 'masks' folder with post_disaster PNGs
    for search_dir in [input_path] + sorted(input_path.rglob("*")):
        if not search_dir.is_dir():
            continue
        masks_dir = search_dir / "masks"
        images_dir = search_dir / "images"
        if masks_dir.is_dir() and images_dir.is_dir():
            post_masks = list(masks_dir.glob("*_post_disaster.png"))
            if post_masks:
                return masks_dir, images_dir

    raise FileNotFoundError(
        f"Could not find masks/ and images/ directories with *_post_disaster.png "
        f"files under {input_path}. Check that the ZIP was extracted correctly."
    )


def parse_mask(mask_path: Path):
    """Read a damage mask PNG and return (worst_label_3class, pixel_stats).
    Returns ("skip", stats) if the mask has no building pixels at all.
    """
    mask = np.array(Image.open(mask_path))
    unique_vals = np.unique(mask)

    damage_vals = sorted([int(v) for v in unique_vals if int(v) in EBD_TO_3CLASS])

    if not damage_vals:
        pixel_counts = {str(int(v)): int(np.sum(mask == v)) for v in unique_vals}
        return "skip", {"pixel_counts": pixel_counts, "total_pixels": int(mask.size)}

    worst_level = max(damage_vals)
    label_3class = EBD_TO_3CLASS[worst_level]

    pixel_counts = {str(int(v)): int(np.sum(mask == v)) for v in unique_vals}
    building_pixels = sum(int(np.sum(mask == v)) for v in damage_vals)

    stats = {
        "pixel_counts": pixel_counts,
        "total_pixels": int(mask.size),
        "building_pixels": building_pixels,
        "damage_levels_present": damage_vals,
        "worst_level": int(worst_level),
    }

    return label_3class, stats


def main():
    parser = argparse.ArgumentParser(description="Prepare EBD Pakistan Flooding dataset")
    parser.add_argument("--input", required=True, help="Path to extracted EBD Pakistan directory")
    parser.add_argument("--output", required=True, help="Output directory (e.g. data/ebd)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"[ERROR] Input path does not exist: {input_path}")
        sys.exit(1)

    print(f"[1/5] Locating EBD mask/image directories under {input_path} ...")
    masks_dir, images_dir = find_ebd_root(input_path)
    print(f"       Masks dir:  {masks_dir}")
    print(f"       Images dir: {images_dir}")

    mask_files = sorted(masks_dir.glob("*_post_disaster.png"))
    if not mask_files:
        print(f"[ERROR] No *_post_disaster.png files found in {masks_dir}")
        sys.exit(1)

    print(f"[2/5] Found {len(mask_files)} post-disaster mask files")

    output_images = output_path / "images"
    output_images.mkdir(parents=True, exist_ok=True)

    print("[3/5] Processing masks (worst-pixel heuristic + 3-class mapping) ...")
    tiles = []
    class_dist = {"none": 0, "partial": 0, "destroyed": 0}
    skipped = 0
    edge_cases = []

    for idx, mask_path in enumerate(mask_files):
        # mask_path stem: e.g. "PAKISTAN-FLOODING_000017_post_disaster"
        # base_id: full prefix without _post_disaster
        mask_name = mask_path.stem  # "PAKISTAN-FLOODING_000017_post_disaster"
        base_id = mask_name.replace("_post_disaster", "")

        post_img_path = images_dir / f"{base_id}_post_disaster.png"
        if not post_img_path.exists():
            edge_cases.append(f"Missing post-disaster image for {base_id}")
            skipped += 1
            continue

        label, stats = parse_mask(mask_path)

        if label == "skip":
            edge_cases.append(
                f"No building pixels in {base_id} "
                f"(unique vals: {list(stats['pixel_counts'].keys())})"
            )
            skipped += 1
            continue

        output_id = f"{idx:04d}"
        shutil.copy2(str(post_img_path), str(output_images / f"{output_id}.png"))

        tiles.append({
            "output_id": output_id,
            "original_id": base_id,
            "disaster": "pakistan_flooding",
            "label_ebd_worst": label,
            "damage_levels_present": stats["damage_levels_present"],
            "building_pixels": stats["building_pixels"],
            "total_pixels": stats["total_pixels"],
        })

        class_dist[label] += 1

        if (idx + 1) % 500 == 0:
            print(f"       Processed {idx + 1}/{len(mask_files)} ...")

    total_tiles = len(tiles)
    print(f"[4/5] Processed {len(mask_files)} masks -> {total_tiles} tiles ({skipped} skipped)")
    print(f"       Class distribution: {class_dist}")

    if edge_cases:
        print(f"       Edge cases logged: {len(edge_cases)}")

    labels_path = output_path / "labels.csv"
    with open(labels_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label"])
        for tile in tiles:
            writer.writerow([tile["output_id"], tile["label_ebd_worst"]])

    manifest = {
        "source": "EBD (Extensible Building Damage) - Pakistan Flooding subset",
        "source_doi": "10.6084/m9.figshare.25285009.v2",
        "source_paper": "Wang, Wu, Zhang & Xia (2025), DOI: 10.34133/remotesensing.0733",
        "total_tiles": total_tiles,
        "skipped_tiles": skipped,
        "class_distribution": class_dist,
        "label_remapping": {
            "1 (no-damage)": "none",
            "2 (minor-damage)": "partial",
            "3 (major-damage)": "destroyed",
            "4 (destroyed)": "destroyed",
        },
        "label_remapping_note": (
            "major-damage mapped to 'destroyed' (not 'partial'). "
            "Rationale: same as xBD pipeline - major-damage is closer to 'needs urgent aid'."
        ),
        "tile_level_labeling": "worst (highest severity) pixel label per tile",
        "resolution": "512x512 RGB",
        "edge_cases": edge_cases[:50],
        "tiles": tiles,
    }

    manifest_path = output_path / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[5/5] Output written to {output_path}")
    print(f"       labels.csv: {labels_path} ({total_tiles} rows)")
    print(f"       manifest.json: {manifest_path}")
    print(f"       images/: {output_images} ({total_tiles} PNGs)")

    if edge_cases:
        print(f"\n[WARN] {len(edge_cases)} edge cases encountered (first 10):")
        for ec in edge_cases[:10]:
            print(f"       - {ec}")
        if len(edge_cases) > 10:
            print(f"       ... and {len(edge_cases) - 10} more (see manifest.json)")

    return 0 if total_tiles > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
