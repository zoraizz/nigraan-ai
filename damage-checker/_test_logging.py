"""Quick test: send requests to /classify-damage and verify prediction logging."""
import requests
import csv

BASE = "http://127.0.0.1:8001"
DATA_DIR = "data/xbd/images"

# Test images with known ground truth (from labels.csv)
test_cases = [
    ("0000.png", "Karachi"),     # ground truth: destroyed
    ("0001.png", "Hyderabad"),   # ground truth: none
    ("0002.png", "Sukkur"),      # ground truth: partial
    ("0003.png", "Larkana"),     # ground truth: none
    ("0006.png", "Quetta"),      # ground truth: destroyed
]

# Also test with an unknown filename (no ground truth)
test_cases.append(("unknown_satellite_image.png", "Nowhere"))

for filename, area in test_cases:
    path = f"{DATA_DIR}/{filename}"
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                f"{BASE}/classify-damage",
                files={"image": (filename, f, "image/png")},
                params={"area": area},
            )
        print(f"  {filename:30s} -> {resp.json()}")
    except FileNotFoundError:
        # For unknown filename, use a real file but rename it
        with open(f"{DATA_DIR}/0010.png", "rb") as f:
            resp = requests.post(
                f"{BASE}/classify-damage",
                files={"image": (filename, f, "image/png")},
                params={"area": area},
            )
        print(f"  {filename:30s} -> {resp.json()}")

# Print the log
print("\n--- predictions_log.csv ---")
with open("predictions_log.csv") as f:
    reader = csv.reader(f)
    for row in reader:
        print("  " + " | ".join(row))
