"""
Build-time WebP derivatives of the cover art.

The originals in images/ total ~41 MB, far too much for an index of 62 covers.
Each cover is resized into a couple of WebP sizes, cached by source mtime so
repeat builds are nearly free.

Pillow is optional: without it the build still runs and falls back to the
original images, so the site never fails to build over a missing dependency.
"""

import shutil
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache" / "thumbs"

try:
    from PIL import Image, ImageOps
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


class Derivative(NamedTuple):
    url: str
    width: int
    height: int


# kind -> (widths, aspect ratio, quality)
SPECS = {
    "card": ((480, 960), (1, 1), 72),
    "hero": ((960, 1440, 1920), (16, 10), 62),
}

# Subjects in this artwork tend to sit above the middle, so bias the crop up
CENTERING = (0.5, 0.45)


def available() -> bool:
    return HAVE_PIL


def _render(src: Path, dest: Path, w: int, h: int, quality: int, centering):
    cached = CACHE / f"{src.stem}-{w}x{h}-q{quality}-{src.stat().st_mtime_ns}.webp"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        img = ImageOps.exif_transpose(Image.open(src))
        if img.mode != "RGB":
            img = img.convert("RGB")
        out = ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=centering)
        out.save(cached, "WEBP", quality=quality, method=4)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, dest)


def derive(src: Path, out_dir: Path, kind: str = "card",
           centering=CENTERING) -> list[Derivative]:
    """Write the derivatives for one image and return them, widest last."""
    widths, (rw, rh), quality = SPECS[kind]
    if not HAVE_PIL:
        return []

    results = []
    for w in widths:
        h = round(w * rh / rw)
        name = f"{src.stem}-{kind}-{w}.webp"
        _render(src, out_dir / name, w, h, quality, centering)
        results.append(Derivative(f"/img/t/{name}", w, h))
    return results
