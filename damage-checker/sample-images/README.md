# Sample Images — Damage Checker Demonstration

Five post-disaster satellite tiles with known ground-truth damage labels, so anyone
can see the Damage Checker's real input/output behavior without setting up any
datasets. Each image below was sent through a live `POST /classify-damage` running
the v3 checkpoint (`checkpoints/xbd_ebd_v3.pth`); predictions were recorded on
2026-09-04 and are deterministic per checkpoint.

| File | Source dataset | Disaster / region | Ground truth | Prediction (confidence) | Match |
|------|----------------|-------------------|--------------|------------------------|-------|
| `PAKISTAN-FLOODING_018024_post_disaster.png` | EBD Pakistan Flooding, test split | River flooding, Pakistan (July 2022 floods) | none | none (0.5076) | yes |
| `PAKISTAN-FLOODING_011306_post_disaster.png` | EBD Pakistan Flooding, test split | River flooding, Pakistan (July 2022 floods) | partial | none (0.5922) | no |
| `PAKISTAN-FLOODING_014695_post_disaster.png` | EBD Pakistan Flooding, test split | River flooding, Pakistan (July 2022 floods) | destroyed | destroyed (0.5406) | yes |
| `joplin-tornado_00000120_post_disaster.png` | xBD (xView2), validation split | Tornado, Joplin, Missouri, USA | destroyed | destroyed (0.9849) | yes |
| `santa-rosa-wildfire_00000138_post_disaster.png` | xBD (xView2), validation split | Wildfire, Santa Rosa, California, USA | destroyed | destroyed (0.6429) | yes |

## Why these five

- The three Pakistan tiles come from the **EBD test split** (`data/splits_v3.json`),
  which was held out from v3 training, so their predictions are a genuine
  out-of-sample check on the target region. They cover all three classes of the
  API contract (none / partial / destroyed).
- The two xBD tiles come from the **xBD validation split** and from disaster types
  absent from the Pakistan data (tornado, wildfire), demonstrating cross-disaster
  generalization. The Joplin tornado tile is a high-confidence hit on catastrophic,
  clearly visible damage (debris fields, exposed foundations).
- The single miss is the documented weak *partial* class — flood imagery with minor
  damage is the model's bottleneck (see "Known weak points" in the main README).
  It is included deliberately: a demonstration folder should show the failure
  modes, not only the wins.
- All filenames are the original dataset filenames. EBD tiles are byte-identical
  copies of the released dataset images; xBD tiles are byte-identical copies from
  the local xBD archives (pixel-verified against the training copies).

## Ground-truth labeling

Both source datasets use 4-level damage scales, remapped to the shared 3-class
contract during data preparation (`prepare_ebd_data.py` / `prepare_xbd_data.py`):
minor-damage maps to *partial*, and major-damage maps to *destroyed* (closer to
"needs urgent aid"). Tile labels take the worst severity present in the tile
(worst building polygon for xBD, worst pixel for EBD). Full rationale lives in the
main README's Damage Checker section.

## Reproduce

Start the service (see `dashboard/INTEGRATION.md` or `.env.example`), then:

```bash
curl -X POST http://localhost:8001/classify-damage \
  -F "image=@sample-images/joplin-tornado_00000120_post_disaster.png"
```

```json
{"damage_level":"destroyed","confidence":0.9849,"area":"unknown"}
```

## Sources

- **EBD Pakistan Flooding** — Wang, Wu, Zhang & Xia (2025), *Journal of Remote
  Sensing*, DOI 10.34133/remotesensing.0733; Figshare DOI
  10.6084/m9.figshare.25285009. 512x512 RGB Maxar Open Data imagery with
  pixel-level damage masks, July 2022 Pakistan floods.
- **xBD (xView2)** — xView2 Challenge dataset (xview2.org). 1024x1024 RGB
  post-disaster tiles with per-building polygon damage labels.
