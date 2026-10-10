import requests
import time
import sys

print('Polling Render deploy...')
while True:
    try:
        res = requests.post(
            'https://nigraan-damage-checker.onrender.com/classify-damage',
            files={'image': ('t.png', b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82', 'image/png')}
        ).json()
        t = res.get('ood', {}).get('photo_score_threshold')
        if t == 1.65:
            print('Deployed! Threshold:', t)
            break
        print('Still', t)
    except Exception as e:
        print('Error:', e)
    time.sleep(15)
