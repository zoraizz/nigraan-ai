"""Quick check: what threshold is the live endpoint serving?"""
import io, requests, json
from PIL import Image
import numpy as np

# Create a tiny valid PNG
img = Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8))
buf = io.BytesIO()
img.save(buf, format="PNG")
buf.seek(0)

r = requests.post(
    "https://nigraan-damage-checker.onrender.com/classify-damage",
    files={"image": ("test.png", buf, "image/png")},
    params={"area": "test"},
    timeout=120,
)
data = r.json()
print(json.dumps(data, indent=2))
ood = data.get("ood", {})
print(f"\nLive photo_score_threshold: {ood.get('photo_score_threshold')}")
print(f"Expected after fix: 1.65")
print(f"Old (broken): 1.9")
