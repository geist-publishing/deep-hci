#!/usr/bin/env python3
"""
Publish (or schedule) a new episode: upload the audio as a GitHub release asset,
add the episode to episodes.yaml, then commit and push. The GitHub Action
rebuilds the site; scheduled episodes appear once their date has passed.

Usage:
    python publish_episode.py --title "CHI 2026 ..." --description desc.html \\
        --audio episode.m4a --image cover.jpg [--at 2026-10-01T08:00Z]

Or from Python: publish(title, description_html, audio_path, image_path, publish_at)
"""

import argparse
import mimetypes
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from episodes_io import ROOT, load_episodes, load_podcast, release_tag, save_episodes

AUDIO_TYPES = {".m4a": "audio/x-m4a", ".mp3": "audio/mpeg"}


def run(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:90].rstrip("-")


def audio_duration(path: Path) -> int:
    out = run("ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path))
    return round(float(out))


def upload_audio(repo: str, tag: str, path: Path):
    """Upload to the yearly release, creating the release if needed."""
    try:
        run("gh", "release", "view", tag, "--repo", repo)
    except subprocess.CalledProcessError:
        run("gh", "release", "create", tag, "--repo", repo,
            "--title", f"Audio {tag.removeprefix('audio-')}",
            "--notes", "Podcast audio files. Served via the RSS feed.")
    run("gh", "release", "upload", tag, str(path), "--repo", repo, "--clobber")


def publish(title: str, description: str, audio_path: str, image_path: str | None = None,
            publish_at: datetime | None = None, push: bool = True) -> dict:
    podcast = load_podcast()
    episodes = load_episodes()
    audio = Path(audio_path)
    publish_at = publish_at or datetime.now(timezone.utc)

    slug = slugify(title)
    if any(e["slug"] == slug for e in episodes):
        raise ValueError(f"An episode with slug '{slug}' already exists")

    # GitHub replaces spaces etc. in asset names, so use a safe name up front
    audio_name = re.sub(r"[^A-Za-z0-9._-]+", "_", audio.name)
    episode = {
        "guid": f"deep-hci.org/{uuid.uuid4()}",
        "title": title,
        "slug": slug,
        "published": publish_at.astimezone(timezone.utc).isoformat(),
        "episode": max((e.get("episode") or 0 for e in episodes), default=0) + 1,
        "duration": audio_duration(audio),
        "audio_file": audio_name,
        "audio_length": audio.stat().st_size,
        "audio_type": AUDIO_TYPES.get(audio.suffix.lower()) or mimetypes.guess_type(audio.name)[0],
        "image": None,
        "description": description.strip(),
    }

    if image_path:
        image = Path(image_path)
        episode["image"] = f"{slug}{image.suffix.lower()}"
        shutil.copy2(image, ROOT / "images" / episode["image"])

    print(f"Uploading {audio.name} to release {release_tag(episode)} ...")
    staged = ROOT / "audio" / episode["published"][:4] / audio_name
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio, staged)
    upload_audio(podcast["audio_repo"], release_tag(episode), staged)

    episodes.insert(0, episode)
    save_episodes(episodes)

    print("Extracting waveform and accent colour ...")
    import build_visuals
    build_visuals.main(only=episode["guid"])

    if push:
        run("git", "add", "episodes.yaml", "visuals.json", "images")
        run("git", "commit", "-m", f"Add episode: {title}")
        run("git", "push")

    print(f"Published: {podcast['site_url']}/e/{slug}/ (live from {episode['published']})")
    return episode


def main():
    parser = argparse.ArgumentParser(description="Publish a podcast episode")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True, help="HTML file with the show notes")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--image")
    parser.add_argument("--at", help="Release time, ISO 8601 (e.g. 2026-10-01T08:00Z). Default: now")
    parser.add_argument("--no-push", action="store_true", help="Don't commit and push")
    args = parser.parse_args()

    publish_at = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else None
    publish(args.title, Path(args.description).read_text(), args.audio, args.image,
            publish_at, push=not args.no_push)


if __name__ == "__main__":
    main()
