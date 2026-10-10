#!/usr/bin/env python3
"""
Transcribe episodes into transcripts/<slug>.json.

Search engines can't hear audio, so the transcripts are what makes 14 hours of
episodes findable. They are committed, rendered into the episode pages at build
time, and linked from the feed as <podcast:transcript>.

Local only — CI never runs this. Incremental by default.

    python transcribe.py [--force] [--only <guid|slug>] [--engine mlx|whisper]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from episodes_io import ROOT, audio_path, load_episodes, transcript_path

VERSION = 1
MODEL = "mlx-community/whisper-large-v3-turbo-q4"


def _segments(result: dict) -> list[dict]:
    """Keep it compact: start, end, text."""
    out = []
    for seg in result.get("segments", []):
        text = seg["text"].strip()
        if text:
            out.append({"s": round(seg["start"], 2), "e": round(seg["end"], 2), "t": text})
    return out


def transcribe_one(ep: dict, engine: str = "mlx") -> dict:
    audio = audio_path(ep)
    if engine == "mlx":
        import mlx_whisper
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=MODEL, language="en", verbose=None)
    else:
        # openai-whisper fallback; much slower, same shape of output
        out_dir = ROOT / ".cache" / "whisper"
        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["whisper", str(audio), "--model", "medium.en", "--language", "en",
                        "--output_format", "json", "--output_dir", str(out_dir)],
                       check=True, capture_output=True)
        result = json.loads((out_dir / f"{audio.stem}.json").read_text())

    segments = _segments(result)
    return {
        "guid": ep["guid"],
        "slug": ep["slug"],
        "version": VERSION,
        "model": MODEL if engine == "mlx" else "openai-whisper/medium.en",
        "language": "en",
        "src": {"audio": ep["audio_file"], "version": VERSION},
        "duration": ep["duration"],
        "word_count": sum(len(s["t"].split()) for s in segments),
        "segments": segments,
    }


def main(force: bool = False, only: str | None = None, engine: str = "mlx"):
    episodes = load_episodes()
    if only:
        episodes = [e for e in episodes if only in (e["guid"], e["slug"])]
        if not episodes:
            raise SystemExit(f"No episode matching {only!r}")

    (ROOT / "transcripts").mkdir(exist_ok=True)
    done = 0
    for ep in episodes:
        dest = transcript_path(ep["slug"])
        if dest.exists() and not force:
            try:
                current = json.loads(dest.read_text())
                if (current.get("version") == VERSION
                        and current.get("src", {}).get("audio") == ep["audio_file"]):
                    continue
            except json.JSONDecodeError:
                pass

        if not audio_path(ep).exists():
            print(f"  skip (no audio): {ep['slug'][:60]}", file=sys.stderr)
            continue

        started = time.time()
        data = transcribe_one(ep, engine)
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        done += 1
        rate = ep["duration"] / max(time.time() - started, 0.01)
        print(f"  {ep['slug'][:52]:52s} {data['word_count']:5d} words  {rate:4.1f}x realtime")

    print(f"transcripts: {done} written, {len(list((ROOT / 'transcripts').glob('*.json')))} total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe episodes")
    parser.add_argument("--force", action="store_true", help="Redo existing transcripts")
    parser.add_argument("--only", help="A single episode guid or slug")
    parser.add_argument("--engine", default="mlx", choices=["mlx", "whisper"])
    args = parser.parse_args()
    main(force=args.force, only=args.only, engine=args.engine)
