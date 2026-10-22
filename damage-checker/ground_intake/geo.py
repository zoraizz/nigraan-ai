"""Place a ground photo. No network and no disk.

Priority for the coordinates and the source label is exif, then device GPS,
then a district the client typed (manual), then unknown.

GPS (exif or device) also picks the district, but only when the nearest of
the 16 centres is within max_km. Otherwise the client's district is kept,
including when that means leaving it blank. A photo taken between districts
must not be quietly reassigned.

read_exif_gps uses the GPS IFD (tag 0x8825) only. Missing or broken GPS
returns None. strip_exif rebuilds the pixels into a new image so a saved
JPEG does not carry the camera's location or the photographer's identity.
"""

from __future__ import annotations

import math

from PIL import Image

from ground_intake.districts import DISTRICTS

_GPS_IFD = 0x8825
_GPS_LAT_REF = 1
_GPS_LAT = 2
_GPS_LON_REF = 3
_GPS_LON = 4
_EARTH_RADIUS_KM = 6371.0


def _component(value: object) -> float:
    """One EXIF rational or number as a float."""
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denominator = float(value.denominator)
        if denominator == 0:
            return 0.0
        return float(value.numerator) / denominator
    if isinstance(value, tuple) and len(value) == 2 and not isinstance(value[0], (tuple, list)):
        denominator = float(value[1])
        if denominator == 0:
            return 0.0
        return float(value[0]) / denominator
    return float(value)  # type: ignore[arg-type]


def _dms_to_degrees(dms: object) -> float | None:
    if not isinstance(dms, (tuple, list)) or not dms:
        return None
    degrees = _component(dms[0])
    minutes = _component(dms[1]) if len(dms) > 1 else 0.0
    seconds = _component(dms[2]) if len(dms) > 2 else 0.0
    return degrees + minutes / 60.0 + seconds / 3600.0


def _ref(value: object) -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    if value is None:
        return ""
    return str(value).strip().upper()[:1]


def _signed_dms(dms: object, ref: object, negative_ref: str) -> float | None:
    degrees = _dms_to_degrees(dms)
    if degrees is None:
        return None
    if _ref(ref) == negative_ref:
        return -abs(degrees)
    return degrees


def read_exif_gps(pil_image: Image.Image) -> tuple[float, float] | None:
    """(lat, lon) in decimal degrees from the GPS IFD, or None."""
    try:
        gps = pil_image.getexif().get_ifd(_GPS_IFD)
    except Exception:
        return None
    if not gps:
        return None
    try:
        lat = _signed_dms(gps.get(_GPS_LAT), gps.get(_GPS_LAT_REF), "S")
        lon = _signed_dms(gps.get(_GPS_LON), gps.get(_GPS_LON_REF), "W")
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return None
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def _pixels(image: Image.Image) -> list:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def strip_exif(pil_image: Image.Image) -> Image.Image:
    """Copy the pixels and nothing else. The result has no EXIF."""
    clean = Image.new(pil_image.mode, pil_image.size)
    clean.putdata(_pixels(pil_image))
    return clean


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_district(lat: float, lon: float, max_km: float) -> str | None:
    """Name of the closest district centre within max_km, or None.

    Ties keep the earlier entry in DISTRICTS. A distance equal to max_km
    counts as within.
    """
    best_name: str | None = None
    best_km: float | None = None
    for district in DISTRICTS:
        km = haversine_km(lat, lon, float(district["lat"]), float(district["lon"]))
        if best_km is None or km < best_km:
            best_name = str(district["name"])
            best_km = km
    if best_name is None or best_km is None or best_km > max_km:
        return None
    return best_name


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_location(
    exif_gps: tuple[float, float] | None,
    client_lat: float | None,
    client_lon: float | None,
    client_district: str | None,
    village: str | None,
    max_km: float,
) -> dict:
    """Location dict. Source is exif > device > manual > unknown.

    When coordinates are known, the district becomes the nearest centre
    inside max_km. Outside that radius the client's district is left as
    they sent it.
    """
    typed_district = _text(client_district)
    typed_village = _text(village)

    lat: float | None = None
    lon: float | None = None
    if exif_gps is not None:
        lat, lon = exif_gps
        source = "exif"
    elif client_lat is not None and client_lon is not None:
        lat, lon = client_lat, client_lon
        source = "device"
    elif typed_district is not None:
        source = "manual"
    else:
        source = "unknown"

    district = typed_district
    if lat is not None and lon is not None:
        nearest = nearest_district(lat, lon, max_km)
        if nearest is not None:
            district = nearest

    return {
        "lat": lat,
        "lon": lon,
        "source": source,
        "district": district,
        "village": typed_village,
    }
