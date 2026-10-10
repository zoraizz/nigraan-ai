"""Deep dive: what does the worst-label heuristic actually do?"""
import json
from collections import Counter

with open("data/xbd/manifest.json") as f:
    manifest = json.load(f)

# 1. For tiles labeled "destroyed", how many buildings on average?
by_label = {"none": [], "partial": [], "destroyed": []}
for tile in manifest["tiles"]:
    by_label[tile["label_xbd_majority"]].append(tile["num_buildings"])

for label in ["none", "partial", "destroyed"]:
    counts = by_label[label]
    if counts:
        print(f"'{label}' tiles: {len(counts)} tiles, "
              f"avg {sum(counts)/len(counts):.0f} buildings, "
              f"range [{min(counts)}-{max(counts)}]")

# 2. The critical question: for a "destroyed" tile with many buildings,
#    is it possible only 1 of 50 buildings is destroyed?
#    Let's check the xBD source data for a specific example.
print("\n--- Worst-case analysis: tiles labeled 'destroyed' ---")
destroyed_tiles = sorted(
    [t for t in manifest["tiles"] if t["label_xbd_majority"] == "destroyed"],
    key=lambda t: t["num_buildings"],
    reverse=True,
)
print(f"Top 5 'destroyed' tiles by building count:")
for t in destroyed_tiles[:5]:
    print(f"  {t['output_id']}: {t['num_buildings']} buildings, "
          f"disaster={t['disaster']}")

# 3. Parse a high-building-count tile to see actual label distribution
import os
tile = destroyed_tiles[0]
orig_id = tile["original_id"]
label_path = f"xbd_raw/train/train/labels/{orig_id}_post_disaster.json"
if os.path.exists(label_path):
    with open(label_path) as f:
        data = json.load(f)
    buildings = data.get("features", {}).get("xy", [])
    labels = [b.get("properties", {}).get("subtype", "?") for b in buildings]
    dist = Counter(labels)
    print(f"\nTile {tile['output_id']} ({orig_id}): {len(buildings)} buildings")
    print(f"  Label distribution: {dict(dist)}")
    print(f"  Our label: '{tile['label_xbd_majority']}' (worst = highest severity)")
    undamaged = dist.get("no-damage", 0)
    total = len(buildings)
    print(f"  {undamaged}/{total} ({100*undamaged/total:.0f}%) buildings are undamaged!")
    print(f"  -> Model learns this ENTIRE tile as 'destroyed' even though most buildings are fine")
