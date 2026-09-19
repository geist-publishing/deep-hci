#!/usr/bin/env python3
"""
One-time export of the podcast from Podbean into episodes.yaml + local files.

- Published episodes come from the live RSS feed (keeps GUIDs, dates, durations).
- Unpublished drafts come from the Podbean API (marked `draft: true`).
- Audio is downloaded to audio/<year>/ (uploaded later by upload_audio.py),
  episode images to images/.
"""

import re
import sys
import time
import uuid
import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from episodes_io import save_episodes

ROOT = Path(__file__).parent
FEED_URL = "https://www.deep-hci.org/feed.xml"
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def download(url: str, dest: Path):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {dest.relative_to(ROOT)}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)


def slug_from_link(link: str) -> str:
    return urlparse(link).path.strip("/").removeprefix("e/")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:90].rstrip("-")


def fetch_image(url: str) -> str | None:
    if not url:
        return None
    name = Path(urlparse(url).path).name
    download(url, ROOT / "images" / name)
    return name


def fetch_audio(url: str, year: int) -> str:
    name = Path(urlparse(url).path).name
    download(url, ROOT / "audio" / str(year) / name)
    return name


def episodes_from_feed() -> list[dict]:
    root = ET.fromstring(requests.get(FEED_URL, timeout=60).content)
    channel = root.find("channel")
    logo = channel.find("itunes:image", NS).get("href")
    download(logo, ROOT / "images" / "logo.jpg")

    episodes = []
    for item in channel.findall("item"):
        enc = item.find("enclosure")
        published = email.utils.parsedate_to_datetime(item.findtext("pubDate"))
        img = item.find("itunes:image", NS)
        ep_no = item.findtext("itunes:episode", namespaces=NS)
        episodes.append({
            "guid": item.findtext("guid"),
            "title": item.findtext("title"),
            "slug": slug_from_link(item.findtext("link")),
            "published": published.isoformat(),
            "episode": int(ep_no) if ep_no else None,
            "duration": int(item.findtext("itunes:duration", namespaces=NS) or 0),
            "audio_file": fetch_audio(enc.get("url"), published.year),
            "audio_length": int(enc.get("length")),
            "audio_type": enc.get("type"),
            "image": fetch_image(img.get("href") if img is not None else None),
            "description": (item.findtext("content:encoded", namespaces=NS)
                            or item.findtext("description") or "").strip(),
        })
    return episodes


def drafts_from_api(known_titles: set[str]) -> list[dict]:
    sys.path.insert(0, str(ROOT.parent))
    from podbean_api import PodbeanAPI

    api = PodbeanAPI()
    api.authenticate()
    result = api.get_episodes(limit=100)

    drafts = []
    for ep in result.get("episodes", []):
        if ep["status"] == "publish" or ep["title"] in known_titles:
            continue
        published = datetime.fromtimestamp(ep["publish_time"], tz=timezone.utc)
        audio_file = fetch_audio(ep["media_url"], published.year)
        audio_path = ROOT / "audio" / str(published.year) / audio_file
        drafts.append({
            "guid": f"deep-hci.org/{uuid.uuid4()}",
            "title": ep["title"],
            "slug": slugify(ep["title"]),
            "published": published.isoformat(),
            "episode": ep.get("episode_number") or None,
            "duration": int(ep.get("duration") or 0),
            "audio_file": audio_file,
            "audio_length": audio_path.stat().st_size,
            "audio_type": "audio/x-m4a",
            "image": fetch_image(ep.get("logo")),
            "description": ep["content"].strip(),
            "draft": True,
        })
    return drafts


def main():
    print(f"Reading {FEED_URL} ...")
    episodes = episodes_from_feed()
    print(f"  {len(episodes)} published episodes")

    print("Reading drafts from Podbean API ...")
    drafts = drafts_from_api({e["title"] for e in episodes})
    print(f"  {len(drafts)} drafts")

    all_eps = sorted(episodes + drafts, key=lambda e: e["published"], reverse=True)
    save_episodes(all_eps)
    print(f"Wrote episodes.yaml with {len(all_eps)} episodes")


if __name__ == "__main__":
    main()
