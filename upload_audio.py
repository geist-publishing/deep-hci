#!/usr/bin/env python3
"""
One-time: upload all exported audio in audio/<year>/ to the yearly GitHub
releases (audio-<year>). Skips files that are already uploaded.
"""

import json
from pathlib import Path

from episodes_io import ROOT, load_episodes, load_podcast, release_tag
from publish_episode import run, upload_audio


def existing_assets(repo: str, tag: str) -> set[str]:
    try:
        out = run("gh", "release", "view", tag, "--repo", repo, "--json", "assets")
    except Exception:
        return set()
    return {a["name"] for a in json.loads(out)["assets"]}


def main():
    repo = load_podcast()["github_repo"]
    uploaded: dict[str, set[str]] = {}
    for ep in load_episodes():
        tag = release_tag(ep)
        if tag not in uploaded:
            uploaded[tag] = existing_assets(repo, tag)
        if ep["audio_file"] in uploaded[tag]:
            continue
        path = ROOT / "audio" / tag.removeprefix("audio-") / ep["audio_file"]
        print(f"{tag}: {ep['audio_file']}")
        upload_audio(repo, tag, path)
        uploaded[tag].add(ep["audio_file"])


if __name__ == "__main__":
    main()
