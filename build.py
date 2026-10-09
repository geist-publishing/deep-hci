#!/usr/bin/env python3
"""
Build the static site into _site/: feed.xml, index.html, one page per episode
(at /e/<slug>/, the same URLs Podbean used), images and CNAME.

Episodes marked `draft: true` or dated in the future are left out, so a daily
rebuild (see .github/workflows/pages.yml) releases scheduled episodes.
"""

import email.utils
import sys
import html
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from episodes_io import ROOT, load_episodes, load_podcast, load_visuals, release_tag

OUT = ROOT / "_site"
ASSETS = ROOT / "assets"
TEMPLATES = ROOT / "templates"

# Venue prefixes the episode titles carry, e.g. "IEEE VR 2025 Blind VR: ..."
VENUE_RE = re.compile(r"^((?:[A-Z][A-Za-z&]*\.?\s*){1,3}?)((?:19|20)\d{2})\b[:\s]*")


def audio_url(podcast: dict, ep: dict, op3: bool = True) -> str:
    """Feed enclosures go through OP3 for stats; on-page players link direct."""
    url = (f"https://github.com/{podcast['audio_repo']}/releases/download/"
           f"{release_tag(ep)}/{ep['audio_file']}")
    if op3 and podcast.get("op3"):
        url = "https://op3.dev/e/" + url.removeprefix("https://")
    return url


def venue_of(ep: dict) -> tuple[str, str]:
    """Split "AHs 2025 texTENG: ..." into ("AHs 2025", "texTENG: ...").

    The feed keeps the full title; only the site shows them apart.
    """
    m = VENUE_RE.match(ep["title"])
    if not m or not m.group(1).strip():
        return "", ep["title"]
    venue = re.sub(r"\s+", " ", m.group(1).strip())
    venue = {"AHS": "AHs", "CHI": "CHI"}.get(venue, venue)
    return f"{venue} {m.group(2)}", ep["title"][m.end():].strip() or ep["title"]


def image_url(podcast: dict, name: str) -> str:
    return f"{podcast['site_url']}/img/{name}"


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def visible_episodes() -> list[dict]:
    now = datetime.now(timezone.utc)
    eps = [e for e in load_episodes()
           if not e.get("draft") and datetime.fromisoformat(e["published"]) <= now]
    return sorted(eps, key=lambda e: datetime.fromisoformat(e["published"]), reverse=True)


def build_feed(podcast: dict, eps: list[dict]) -> str:
    esc = html.escape
    site = podcast["site_url"]
    feed_url = site + podcast["feed_path"]
    logo = image_url(podcast, Path(podcast["image"]).name)
    categories = "\n".join(f'    <itunes:category text="{esc(c)}" />' for c in podcast["categories"])
    owner_email = (f"\n      <itunes:email>{esc(podcast['owner_email'])}</itunes:email>"
                   if podcast.get("owner_email") else "")
    last = email.utils.format_datetime(datetime.fromisoformat(eps[0]["published"])) if eps else ""

    items = []
    for ep in eps:
        link = f"{site}/e/{ep['slug']}/"
        episode_no = f"\n      <itunes:episode>{ep['episode']}</itunes:episode>" if ep.get("episode") else ""
        items.append(f"""    <item>
      <title>{esc(ep['title'])}</title>
      <itunes:title>{esc(ep['title'])}</itunes:title>
      <link>{link}</link>
      <pubDate>{email.utils.format_datetime(datetime.fromisoformat(ep['published']))}</pubDate>
      <guid isPermaLink="false">{esc(ep['guid'])}</guid>
      <description>{cdata(ep['description'])}</description>
      <content:encoded>{cdata(ep['description'])}</content:encoded>
      <enclosure url="{esc(audio_url(podcast, ep))}" length="{ep['audio_length']}" type="{ep['audio_type']}"/>
      <itunes:summary>{cdata(plain(ep['description']))}</itunes:summary>
      <itunes:author>{esc(podcast['author'])}</itunes:author>
      <itunes:explicit>{str(podcast['explicit']).lower()}</itunes:explicit>
      <itunes:duration>{ep['duration']}</itunes:duration>{episode_no}
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:image href="{image_url(podcast, ep['image']) if ep.get('image') else logo}" />
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>{esc(podcast['title'])}</title>
    <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>
    <link>{site}</link>
    <description>{esc(podcast['description'])}</description>
    <pubDate>{last}</pubDate>
    <lastBuildDate>{email.utils.format_datetime(datetime.now(timezone.utc))}</lastBuildDate>
    <language>{podcast['language']}</language>
    <copyright>{esc(podcast['copyright'])}</copyright>
    <ttl>1440</ttl>
    <itunes:type>episodic</itunes:type>
    <itunes:summary>{esc(podcast['description'])}</itunes:summary>
    <itunes:author>{esc(podcast['author'])}</itunes:author>
{categories}
    <itunes:owner>
      <itunes:name>{esc(podcast['owner_name'])}</itunes:name>{owner_email}
    </itunes:owner>
    <itunes:explicit>{str(podcast['explicit']).lower()}</itunes:explicit>
    <itunes:new-feed-url>{feed_url}</itunes:new-feed-url>
    <itunes:image href="{logo}" />
    <image>
      <url>{logo}</url>
      <title>{esc(podcast['title'])}</title>
      <link>{site}</link>
    </image>
{chr(10).join(items)}
  </channel>
</rss>
"""


# ---------------------------------------------------------------- templates

_tpl_cache: dict[str, str] = {}


def tpl(name: str) -> str:
    if name not in _tpl_cache:
        _tpl_cache[name] = (TEMPLATES / name).read_text()
    return _tpl_cache[name]


def render(template: str, **vars: str) -> str:
    """Replace {{ key }}. Not str.format — CSS and JS are full of braces."""
    def sub(m):
        key = m.group(1).strip()
        if key not in vars:
            raise KeyError(f"no value for {{{{{key}}}}}")
        return str(vars[key])
    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", sub, template)


def page(podcast: dict, title: str, description: str, body: str, og_image: str) -> str:
    return render(
        tpl("base.html"),
        lang=podcast["language"],
        title=html.escape(title),
        show=html.escape(podcast["title"]),
        description=html.escape(plain(description))[:200],
        feed_path=podcast["feed_path"],
        logo=Path(podcast["image"]).name,
        author=html.escape(podcast["author"]),
        og_image=og_image,
        body=body,
    )


# ---------------------------------------------------------------- waveform

def wave_svg(peaks: list[int], bars: int) -> str:
    """Bars drawn twice: once muted, once in the accent and clipped to progress."""
    if bars < len(peaks):
        # Average, not max — maxing saturates every bar and flattens the shape
        step = len(peaks) / bars
        peaks = [round(sum(chunk) / len(chunk))
                 for i in range(bars)
                 if (chunk := peaks[int(i * step):int((i + 1) * step)] or [0])]

    top = max(peaks) or 1
    peaks = [min(100, round(p * 96 / top)) for p in peaks]

    n = len(peaks)
    slot = 100 / n
    width = slot * 0.62
    rects = []
    for i, p in enumerate(peaks):
        h = max(2.0, p)                       # viewBox is 0..100 tall
        y = (100 - h) / 2
        rects.append(f'<rect x="{i * slot + (slot - width) / 2:.3f}" y="{y:.2f}" '
                     f'width="{width:.3f}" height="{h:.2f}" rx="{width / 2:.3f}"/>')
    body = "".join(rects)
    return (f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
            f'<g class="bars">{body}</g><g class="played">{body}</g></svg>')


def wave(podcast: dict, ep: dict, visuals: dict, bars: int, label: str) -> str:
    entry = visuals.get("episodes", {}).get(ep["guid"])
    if not entry:
        print(f"  no visuals for {ep['slug']} — plain row", file=sys.stderr)
        return ""
    accent = entry.get("accent", {}).get("dark", "#61b2d1")
    return (
        f'<div class="wave" role="slider" tabindex="0" aria-label="{html.escape(label)}" '
        f'aria-valuemin="0" aria-valuemax="{ep["duration"]}" aria-valuenow="0" '
        f'data-src="{html.escape(audio_url(podcast, ep, op3=False))}" '
        f'data-duration="{ep["duration"]}" data-accent="{accent}">'
        f'{wave_svg(entry["peaks"], bars)}</div>'
    )


def accent_of(ep: dict, visuals: dict, theme: str = "dark") -> str:
    entry = visuals.get("episodes", {}).get(ep["guid"], {})
    return entry.get("accent", {}).get(theme, "#61b2d1")


# ---------------------------------------------------------------- pages

def build_index(podcast: dict, eps: list[dict], visuals: dict) -> str:
    esc = html.escape
    hero = eps[0]
    _, hero_title = venue_of(hero)

    years = []
    for year in sorted({e["published"][:4] for e in eps[1:]}, reverse=True):
        rows = []
        for ep in [e for e in eps[1:] if e["published"][:4] == year]:
            venue, short = venue_of(ep)
            date = datetime.fromisoformat(ep["published"]).strftime("%b %-d")
            meta = f"{date} — {venue}" if venue else date
            rows.append(f"""<li class="row" style="--row-accent: {accent_of(ep, visuals)}">
  <button class="play" aria-pressed="false" aria-label="Play {esc(short)}">
    <svg class="play-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>
    <svg class="pause-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5h4v13H3zM9 1.5h4v13H9z"/></svg>
  </button>
  <h3 class="title"><a href="/e/{ep['slug']}/">{esc(short)}</a></h3>
  <p class="meta">{esc(meta)} — {fmt_duration(ep['duration'])}</p>
  {wave(podcast, ep, visuals, 128, f"Scrub {short}")}
</li>""")
        years.append(f'<section class="venue reveal"><h2>{year}</h2>'
                     f'<ul class="episodes">{"".join(rows)}</ul></section>')

    body = render(
        tpl("index.html"),
        show=esc(podcast["title"]),
        description=esc(podcast["description"]),
        feed_path=podcast["feed_path"],
        subscribe="".join(
            [f'<a href="{podcast["feed_path"]}">RSS feed</a>']
            + [f'<a href="{esc(url)}">{esc(name)}</a>'
               for name, url in (podcast.get("links") or {}).items()]),
        hero_accent=accent_of(hero, visuals),
        hero_slug=hero["slug"],
        hero_title=esc(hero_title),
        hero_title_plain=esc(hero_title),
        hero_duration=fmt_duration(hero["duration"]),
        hero_wave=wave(podcast, hero, visuals, 180, f"Scrub {hero_title}"),
        years="".join(years),
    )
    return page(podcast, podcast["title"], podcast["description"], body,
                image_url(podcast, Path(podcast["image"]).name))


def build_episode_page(podcast: dict, ep: dict, visuals: dict) -> str:
    esc = html.escape
    venue, short = venue_of(ep)
    image = ep.get("image") or Path(podcast["image"]).name
    body = render(
        tpl("episode.html"),
        accent=accent_of(ep, visuals),
        image=image,
        title=esc(short),
        date=datetime.fromisoformat(ep["published"]).strftime("%B %-d, %Y"),
        venue=f" — {esc(venue)}" if venue else "",
        number=ep.get("episode") or "—",
        wave=wave(podcast, ep, visuals, 240, f"Scrub {short}"),
        duration=fmt_duration(ep["duration"]),
        notes=ep["description"],
        audio=esc(audio_url(podcast, ep, op3=False)),
        size=f"{ep['audio_length'] / 1e6:.0f} MB",
    )
    return page(podcast, f"{short} — {podcast['title']}", ep["description"], body,
                image_url(podcast, image))


def main():
    podcast = load_podcast()
    eps = visible_episodes()
    visuals = load_visuals()

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "img").mkdir(parents=True)

    used_images = {e["image"] for e in eps if e.get("image")} | {Path(podcast["image"]).name}
    for name in used_images:
        shutil.copy2(ROOT / "images" / name, OUT / "img" / name)

    for asset in ASSETS.iterdir():
        shutil.copy2(asset, OUT / asset.name)

    (OUT / podcast["feed_path"].lstrip("/")).write_text(build_feed(podcast, eps))
    (OUT / "index.html").write_text(build_index(podcast, eps, visuals))
    for ep in eps:
        d = OUT / "e" / ep["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(build_episode_page(podcast, ep, visuals))

    (OUT / "CNAME").write_text(urlparse(podcast["site_url"]).hostname + "\n")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(eps)} episodes into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
