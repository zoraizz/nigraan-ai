"""Test the deployed OOD guard by uploading a person-like image."""
import io
import json
import sys
import requests
import numpy as np
from PIL import Image, ImageDraw

def make_person_photo():
    """Create a realistic person-like image."""
    arr = np.full((512, 512, 3), [220, 200, 190], dtype=np.uint8)
    rng = np.random.default_rng(123)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    draw.rectangle((180, 200, 330, 500), fill=(50, 50, 120))
    draw.ellipse((210, 100, 300, 200), fill=(200, 160, 130))
    draw.ellipse((230, 135, 245, 148), fill=(60, 40, 30))
    draw.ellipse((265, 135, 280, 148), fill=(60, 40, 30))
    draw.ellipse((205, 90, 305, 160), fill=(40, 30, 20))
    draw.rectangle((0, 350, 512, 512), fill=(180, 160, 140))
    a = np.array(img).astype(np.int16) + rng.integers(-15, 15, (512, 512, 3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def test_endpoint(url):
    img = make_person_photo()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    print(f"Uploading person photo to {url}/classify-damage ...")
    resp = requests.post(
        f"{url}/classify-damage",
        files={"image": ("person_test.png", buf, "image/png")},
        params={"area": "test"},
        timeout=120,
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2))
    
    if data.get("is_out_of_domain"):
        print("\n✓ CORRECTLY FLAGGED as out-of-domain")
    else:
        print("\n✗ MISSED — not flagged as out-of-domain!")
    return data

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://nigraan-damage-checker.onrender.com"
    test_endpoint(url)
