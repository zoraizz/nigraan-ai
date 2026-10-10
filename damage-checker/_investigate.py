"""Investigation: what do training tiles actually look like?"""
import json
from PIL import Image
from pathlib import Path

# 1. Check actual xBD tile dimensions
raw_img = Image.open("xbd_raw/train/train/images/hurricane-harvey_00000000_post_disaster.png")
print(f"Raw xBD tile size: {raw_img.size}")

# 2. Check prepared tile dimensions
prep_img = Image.open("data/xbd/images/0000.png")
print(f"Prepared tile size: {prep_img.size}")

# 3. Check how many buildings per tile (from manifest)
with open("data/xbd/manifest.json") as f:
    manifest = json.load(f)

building_counts = [t["num_buildings"] for t in manifest["tiles"]]
print(f"\nBuildings per tile stats:")
print(f"  Min: {min(building_counts)}")
print(f"  Max: {max(building_counts)}")
print(f"  Mean: {sum(building_counts)/len(building_counts):.1f}")
print(f"  Median: {sorted(building_counts)[len(building_counts)//2]}")

# Distribution
from collections import Counter
dist = Counter(building_counts)
print(f"\nBuildings-per-tile distribution (top 10):")
for count, freq in sorted(dist.items())[:10]:
    print(f"  {count:3d} buildings: {freq:3d} tiles")
print(f"  ... ({len(dist)} unique values total)")

# 4. How many tiles have >1 building? (i.e., NOT single-building crops)
multi = sum(1 for b in building_counts if b > 1)
print(f"\nTiles with >1 building: {multi}/{len(building_counts)} ({100*multi/len(building_counts):.1f}%)")
print(f"Tiles with exactly 1 building: {sum(1 for b in building_counts if b == 1)}/{len(building_counts)}")

# 5. Check what the worst-label approach means
# How many tiles have mixed damage (multiple label types)?
mixed = 0
for tile in manifest["tiles"]:
    # We only stored the worst label, but we can check num_buildings
    # A tile with 50 buildings all "no-damage" vs 1 "destroyed" both get "destroyed"
    pass
print(f"\nAll tiles are full 1024x1024 scene tiles, NOT cropped to individual buildings.")
print(f"The label is the WORST building damage in the entire tile.")
