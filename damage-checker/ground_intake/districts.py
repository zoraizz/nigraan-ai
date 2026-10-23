"""District centres used to place a ground photo when GPS is present.

The 16 names and coordinates are copied from dashboard/src/config/districts.js
(coords there are [lat, lon]). Keep in sync with that file and with the Risk
Flag DISTRICTS dict it mirrors.

This module is data only. Distance and "which district is this point in?"
live in geo.py so the table can be checked without doing any I/O.
"""

from __future__ import annotations

# Keep in sync with dashboard/src/config/districts.js.
DISTRICTS: list[dict[str, float | str]] = [
    # Flood (Sindh)
    {"name": "Dadu", "lat": 26.73033, "lon": 67.7769},
    {"name": "Khairpur", "lat": 27.52948, "lon": 68.75915},
    {"name": "Sukkur", "lat": 27.70323, "lon": 68.85889},
    {"name": "Larkana", "lat": 27.55898, "lon": 68.21204},
    {"name": "Jacobabad", "lat": 28.28187, "lon": 68.43761},
    # Flood / hill-torrent (Balochistan & Punjab)
    {"name": "Jaffarabad", "lat": 28.37473, "lon": 68.35032},
    {"name": "D.I. Khan", "lat": 31.83129, "lon": 70.9017},
    {"name": "D.G. Khan", "lat": 30.04587, "lon": 70.64029},
    {"name": "Rajanpur", "lat": 29.10408, "lon": 70.32969},
    # GLOF / avalanche (Gilgit-Baltistan & KP north)
    {"name": "Chitral", "lat": 35.8518, "lon": 71.78636},
    {"name": "Hunza", "lat": 36.32692, "lon": 74.66141},
    {"name": "Skardu", "lat": 35.29787, "lon": 75.63372},
    # Landslide (KP north)
    {"name": "Mansehra", "lat": 34.33023, "lon": 73.19679},
    {"name": "Battagram", "lat": 34.67719, "lon": 73.02329},
    # Drought (Balochistan & Sindh)
    {"name": "Chagai", "lat": 29.35393, "lon": 64.69751},
    {"name": "Tharparkar", "lat": 24.73701, "lon": 69.79707},
]
