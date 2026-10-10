"""
Test the deployed OOD guard with REAL downloaded photos, not synthetic PIL drawings.
Downloads a variety of real-world images and tests them.
"""
import io
import json
import sys
import requests
import numpy as np
from PIL import Image

DEPLOY_URL = "https://nigraan-damage-checker.onrender.com"

# Real photos from the web (public domain / free stock)
TEST_IMAGES = {
    "person_headshot": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=512&h=512&fit=crop",
    "cat": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/512px-Cat03.jpg",
    "city_street": "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?w=512&h=512&fit=crop",
    "office_desk": "https://images.unsplash.com/photo-1518455027359-f3f8164ba6bd?w=512&h=512&fit=crop",
    "food_plate": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=512&h=512&fit=crop",
    "selfie": "https://images.unsplash.com/photo-1494790108755-2616b612b786?w=512&h=512&fit=crop",
    "landscape": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=512&h=512&fit=crop",
}

def download_image(url, name):
    """Download image from URL, return PIL Image."""
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print(f"  [SKIP] {name}: {e}")
        return None

def classify(img, name):
    """Upload image to the deployed endpoint."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    resp = requests.post(
        f"{DEPLOY_URL}/classify-damage",
        files={"image": (f"{name}.png", buf, "image/png")},
        params={"area": "test"},
        timeout=120,
    )
    return resp.json()

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEPLOY_URL
    
    print(f"Testing OOD guard at {url}")
    print("=" * 80)
    
    missed = 0
    tested = 0
    
    for name, img_url in TEST_IMAGES.items():
        print(f"\nDownloading {name}...")
        img = download_image(img_url, name)
        if img is None:
            continue
        
        # Resize to 512x512 to match expected input
        img = img.resize((512, 512))
        
        print(f"  Uploading to {url}/classify-damage ...")
        result = classify(img, name)
        
        flagged = result.get("is_out_of_domain", False)
        pred = result.get("damage_level", "?")
        conf = result.get("confidence", 0)
        ood = result.get("ood", {})
        signals = ood.get("signals", [])
        photo_score = ood.get("photo_score", "N/A")
        
        status = "FLAGGED" if flagged else "** MISSED **"
        print(f"  {name:20s} pred={pred:10s} conf={conf:.3f} "
              f"photo_score={photo_score} signals={signals} -> {status}")
        
        tested += 1
        if not flagged:
            missed += 1
            print(f"  ** WARNING: Real photo not flagged! Full response:")
            print(f"  {json.dumps(result, indent=2)}")
    
    print(f"\n{'='*80}")
    print(f"RESULT: {missed}/{tested} real photos MISSED (not flagged)")
    print(f"{'='*80}")
    return 1 if missed > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
