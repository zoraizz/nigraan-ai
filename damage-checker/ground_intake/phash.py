"""64-bit difference hash for duplicate ground photos.

dHash, not an average hash: a resized 9x8 greyscale thumbnail yields 64
horizontal neighbour comparisons. Photos of the same scene survive a resize
or a mild recompress; a different scene does not. The result is 16 hex
characters so it can be stored on the report and compared with hamming().

Pillow only. No imagehash package and no new dependency.

Bit order is row-major from the top-left. A bit is 1 when the left pixel is
strictly brighter than the pixel to its right. Equal neighbours are 0, so a
flat frame hashes to 0000000000000000. That is intended: dHash measures
gradient, not colour.

The duplicate decision (how close is "the same photo") is not made here.
Callers compare hamming() to their own threshold. Tests treat 8 as "near".
"""

from __future__ import annotations

from PIL import Image

# 8 comparisons across, 8 rows -> 64 bits. The extra column is the right-hand
# neighbour of the last comparison.
_HASH_WIDTH = 9
_HASH_HEIGHT = 8


def _pixels(image: Image.Image) -> list[int]:
    # getdata() is removed in Pillow 14. get_flattened_data() is the replacement.
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def dhash(image: Image.Image) -> str:
    """Return the 64-bit dHash of a Pillow image as 16 lowercase hex chars."""
    grey = image.convert("L").resize(
        (_HASH_WIDTH, _HASH_HEIGHT),
        Image.Resampling.LANCZOS,
    )
    pixels = _pixels(grey)
    bits = 0
    for row in range(_HASH_HEIGHT):
        offset = row * _HASH_WIDTH
        for col in range(_HASH_WIDTH - 1):
            left = pixels[offset + col]
            right = pixels[offset + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    """Count differing bits between two hex hashes."""
    return (int(a, 16) ^ int(b, 16)).bit_count()
