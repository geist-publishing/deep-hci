#!/usr/bin/env python3
"""
Extract per-episode visuals into visuals.json: a waveform (RMS peaks from the
audio) and an accent colour sampled from the cover art.

Run locally after adding an episode; the JSON is committed, so the GitHub Action
needs neither ffmpeg nor Pillow. Incremental by default.

    python build_visuals.py [--force] [--only <guid|slug>]
"""

import argparse
import array
import colorsys
import json
import subprocess
import sys
from pathlib import Path

from episodes_io import ROOT, audio_path, load_episodes, load_visuals, save_visuals

VERSION = 1
PEAK_COUNT = 400

# Theme backgrounds the accent has to stay legible against (see assets/style.css).
# Warm graphite in dark: most covers are cyan-blue, and they sing against a warm base.
DARK_BG = "#1A1917"
LIGHT_BG = "#F4F6F8"
MIN_CONTRAST = 4.5


def peaks(path: Path, n: int = PEAK_COUNT) -> list[int]:
    """RMS envelope, 0..100, normalised to the 97th percentile."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        check=True, capture_output=True).stdout

    samples = array.array("h")
    samples.frombytes(raw[:len(raw) // 2 * 2])
    if not samples:
        raise ValueError(f"no audio decoded from {path}")

    rms = []
    for i in range(n):
        a = len(samples) * i // n
        b = max(len(samples) * (i + 1) // n, a + 1)
        seg = samples[a:b]
        rms.append((sum(v * v for v in seg) / len(seg)) ** 0.5)

    # The 97th percentile, not the max: a single transient would flatten the rest
    ref = sorted(rms)[int(0.97 * (n - 1))] or 1.0
    return [max(2, min(100, round(v * 100 / ref))) for v in rms]


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in (r, g, b))


def _luminance(rgb: tuple[float, float, float]) -> float:
    f = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(_rgb(a)), _luminance(_rgb(b))
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def _fit(h: float, s: float, bg: str, start: float, step: float) -> str:
    """Walk lightness from `start` until the colour is legible on `bg`."""
    lightness = start
    best = _hex(*colorsys.hls_to_rgb(h, lightness, s))
    for _ in range(40):
        candidate = _hex(*colorsys.hls_to_rgb(h, lightness, s))
        if contrast(candidate, bg) >= MIN_CONTRAST:
            return candidate
        best = candidate
        lightness += step
        if not 0.0 <= lightness <= 1.0:
            break
    return best


def accent(image: Path) -> dict[str, str]:
    """Pick the most characteristic colour of the cover, then make it legible."""
    from PIL import Image

    img = Image.open(image).convert("RGB").resize((64, 64))
    quantized = img.convert("P", palette=Image.ADAPTIVE, colors=16).convert("RGB")
    colors = quantized.getcolors(64 * 64) or []

    def score(entry):
        count, (r, g, b) = entry
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return count * (s ** 2) * (1 - abs(l - 0.5) * 1.6)

    count, (r, g, b) = max(colors, key=score)
    h, _, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    s = max(0.55, min(0.90, s))

    return {
        "dark": _fit(h, s, DARK_BG, 0.60, +0.02),
        "light": _fit(h, s, LIGHT_BG, 0.45, -0.02),
    }


def main(force: bool = False, only: str | None = None) -> dict:
    episodes = load_episodes()
    data = load_visuals()
    data.setdefault("version", VERSION)
    data["peak_count"] = PEAK_COUNT
    entries = data.setdefault("episodes", {})

    if only:
        episodes = [e for e in episodes if only in (e["guid"], e["slug"])]
        if not episodes:
            raise SystemExit(f"No episode matching {only!r}")

    for ep in episodes:
        guid = ep["guid"]
        src = {"audio": ep["audio_file"], "image": ep.get("image")}
        current = entries.get(guid)
        if current and not force and current.get("src") == src and data["version"] == VERSION:
            continue

        audio = audio_path(ep)
        if not audio.exists():
            print(f"  skip (no audio): {ep['title'][:60]}", file=sys.stderr)
            continue

        entry = {"peaks": peaks(audio), "src": src}
        if ep.get("image"):
            entry["accent"] = accent(ROOT / "images" / ep["image"])
        entries[guid] = entry
        print(f"  {ep['slug'][:52]:52s} {entry.get('accent', {}).get('dark', '-')}")

    save_visuals(data)
    print(f"visuals.json: {len(entries)} episodes")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build visuals.json")
    parser.add_argument("--force", action="store_true", help="Recompute everything")
    parser.add_argument("--only", help="A single episode guid or slug")
    args = parser.parse_args()
    main(force=args.force, only=args.only)
