#!/usr/bin/env python3
"""
Build the static site into _site/: feed.xml, index.html, one page per episode
(at /e/<slug>/, the same URLs Podbean used), images and CNAME.

Episodes marked `draft: true` or dated in the future are left out, so a daily
rebuild (see .github/workflows/pages.yml) releases scheduled episodes.
"""

import email.utils
import json
import sys
import html
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import thumbnails
from episodes_io import (ROOT, load_episodes, load_podcast, load_transcript, load_visuals,
                         release_tag)

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
        # Apple and Podcasting 2.0 apps show these; only advertise what exists
        tr = load_transcript(ep["slug"])
        transcript_tags = ""
        if tr and tr.get("segments"):
            transcript_tags = (
                f'\n      <podcast:transcript url="{link}transcript.vtt" type="text/vtt" '
                f'language="{podcast["language"]}" rel="captions"/>'
                f'\n      <podcast:transcript url="{link}transcript.json" '
                f'type="application/json" language="{podcast["language"]}" rel="captions"/>')
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
      <itunes:image href="{image_url(podcast, ep['image']) if ep.get('image') else logo}" />{transcript_tags}
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
    <podcast:guid>{uuid.uuid5(uuid.UUID("ead4c236-bf58-58c6-a2c6-a6b28d128cb6"), urlparse(site).hostname + podcast["feed_path"])}</podcast:guid>
    <podcast:medium>podcast</podcast:medium>
    <podcast:locked>no</podcast:locked>
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


def page(podcast: dict, title: str, description: str, body: str, og_image: str, *,
         path: str = "/", og_type: str = "website", head: str = "",
         jsonld: tuple = (), robots: str = "") -> str:
    blocks = "".join(
        '<script type="application/ld+json">'
        + json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")
        + "</script>"
        for obj in jsonld)
    if robots:
        head = f'<meta name="robots" content="{robots}">' + head

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
        og_type=og_type,
        canonical=podcast["site_url"] + path,
        head=head + blocks,
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


def downsample(peaks: list[int], bars: int) -> list[int]:
    if bars < len(peaks):
        step = len(peaks) / bars
        peaks = [round(sum(chunk) / len(chunk))
                 for i in range(bars)
                 if (chunk := peaks[int(i * step):int((i + 1) * step)] or [0])]
    top = max(peaks) or 1
    return [min(100, round(p * 96 / top)) for p in peaks]


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


def wave_data(podcast: dict, ep: dict, visuals: dict, bars: int, label: str) -> str:
    """Same scrubber, but the bars ship as numbers and the player draws them.

    62 inline SVG waveforms cost over a megabyte of markup; this is a few KB.
    """
    entry = visuals.get("episodes", {}).get(ep["guid"])
    if not entry:
        return ""
    peaks = ",".join(str(p) for p in downsample(entry["peaks"], bars))
    return (
        f'<div class="wave" role="slider" tabindex="0" aria-label="{html.escape(label)}" '
        f'aria-valuemin="0" aria-valuemax="{ep["duration"]}" aria-valuenow="0" '
        f'data-src="{html.escape(audio_url(podcast, ep, op3=False))}" '
        f'data-duration="{ep["duration"]}" data-accent="{accent_of(ep, visuals)}" '
        f'data-peaks="{peaks}"></div>'
    )


# ---------------------------------------------------------------- transcripts

def iso_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + f"{s}S"


def group_cues(segments: list[dict], max_sec: float = 35, max_words: int = 65,
               gap: float = 1.2) -> list[dict]:
    """Whisper emits a cue every few seconds; merge them into readable paragraphs."""
    cues, current = [], None
    for seg in segments:
        if (current and seg["s"] - current["e"] < gap
                and seg["e"] - current["s"] < max_sec
                and len(current["t"].split()) < max_words):
            current["t"] += " " + seg["t"]
            current["e"] = seg["e"]
        else:
            if current:
                cues.append(current)
            current = dict(seg)
    if current:
        cues.append(current)
    return cues


def transcript_html(tr: dict | None) -> str:
    """Server-rendered so the words are in the HTML; JS injection wouldn't be indexed."""
    if not tr or not tr.get("segments"):
        return ""
    rows = []
    for cue in group_cues(tr["segments"]):
        stamp = fmt_duration(int(cue["s"]))
        rows.append(
            f'<p><button class="t-cue" data-t="{cue["s"]:.0f}" '
            f'aria-label="Play from {stamp}">{stamp}</button>'
            f'<span>{html.escape(cue["t"])}</span></p>')
    return (
        '<details class="transcript" id="transcript">'
        f'<summary>Transcript <span>{tr["word_count"]:,} words</span></summary>'
        f'<div class="cues">{"".join(rows)}</div></details>')


def vtt(tr: dict) -> str:
    def ts(t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"

    out = ["WEBVTT", ""]
    for i, cue in enumerate(group_cues(tr["segments"]), 1):
        out += [str(i), f"{ts(cue['s'])} --> {ts(cue['e'])}", cue["t"], ""]
    return "\n".join(out)


# ---------------------------------------------------------------- images

def img_tag(derivs: list, fallback: str, *, sizes: str, alt: str,
            cls: str = "", eager: bool = False) -> str:
    """A responsive <img>; falls back to the original when Pillow is absent."""
    attrs = f' class="{cls}"' if cls else ""
    loading = ('loading="eager" fetchpriority="high"' if eager
               else 'loading="lazy" decoding="async"')
    if not derivs:
        return f'<img{attrs} src="{fallback}" alt="{html.escape(alt)}" {loading}>'
    srcset = ", ".join(f"{d.url} {d.width}w" for d in derivs)
    first = derivs[0]
    return (f'<img{attrs} src="{first.url}" srcset="{srcset}" sizes="{sizes}" '
            f'width="{first.width}" height="{first.height}" '
            f'alt="{html.escape(alt)}" {loading}>')


def preload_image(derivs: list, sizes: str) -> str:
    """The hero is the LCP element; without this it waits for the stylesheet."""
    if not derivs:
        return ""
    srcset = ", ".join(f"{d.url} {d.width}w" for d in derivs)
    return (f'<link rel="preload" as="image" href="{derivs[0].url}" '
            f'imagesrcset="{srcset}" imagesizes="{sizes}" fetchpriority="high">')


def cover_derivatives(ep: dict, podcast: dict, out_dir: Path, kind: str) -> list:
    name = ep.get("image") or Path(podcast["image"]).name
    if not thumbnails.available():
        return []
    return thumbnails.derive(ROOT / "images" / name, out_dir, kind)


# ---------------------------------------------------------------- pages

# ---------------------------------------------------------------- venues

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def venue_index(eps: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for ep in eps:
        venue, _ = venue_of(ep)
        if venue:
            groups.setdefault(venue, []).append(ep)
    return groups


def venue_is_indexable(podcast: dict, venue: str, eps: list[dict]) -> bool:
    """A lone episode with no blurb is thin; link it, but don't ask Google to index it."""
    blurb = (podcast.get("venues") or {}).get(venue, {}).get("blurb")
    return len(eps) >= 2 or bool(blurb)


# ---------------------------------------------------------------- structured data

def series_jsonld(podcast: dict, eps: list[dict]) -> dict:
    site = podcast["site_url"]
    return {
        "@context": "https://schema.org",
        "@type": "PodcastSeries",
        "@id": f"{site}/#podcast",
        "name": podcast["title"],
        "url": site + "/",
        "description": plain(podcast["description"]),
        "webFeed": site + podcast["feed_path"],
        "image": image_url(podcast, Path(podcast["image"]).name),
        "inLanguage": podcast["language"],
        "author": {"@type": "Person", "name": podcast["author"]},
        "publisher": {"@type": "Person", "name": podcast["author"]},
        "genre": podcast["categories"],
        "numberOfEpisodes": len(eps),
    }


def episode_jsonld(podcast: dict, ep: dict) -> dict:
    site = podcast["site_url"]
    url = f"{site}/e/{ep['slug']}/"
    data = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "@id": url + "#episode",
        "url": url,
        "name": ep["title"],
        "datePublished": ep["published"],
        "description": plain(ep["description"])[:500],
        "duration": iso_duration(ep["duration"]),
        "timeRequired": iso_duration(ep["duration"]),
        "inLanguage": podcast["language"],
        "image": image_url(podcast, ep.get("image") or Path(podcast["image"]).name),
        "partOfSeries": {"@type": "PodcastSeries", "@id": f"{site}/#podcast",
                         "name": podcast["title"], "url": site + "/"},
        "associatedMedia": {
            "@type": "AudioObject",
            "contentUrl": audio_url(podcast, ep, op3=False),
            "encodingFormat": ep["audio_type"],
            "duration": iso_duration(ep["duration"]),
            "contentSize": str(ep["audio_length"]),
            "uploadDate": ep["published"],
        },
    }
    if ep.get("episode"):
        data["episodeNumber"] = ep["episode"]
    return data


def breadcrumbs(podcast: dict, trail: list[tuple[str, str]]) -> dict:
    site = podcast["site_url"]
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": site + path}
            for i, (name, path) in enumerate(trail, 1)
        ],
    }


PLAY_ICONS = (
    '<svg class="play-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>'
    '<svg class="pause-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5h4v13H3zM9 1.5h4v13H9z"/></svg>'
)

CARD_SIZES = "(min-width: 68rem) 20rem, (min-width: 40rem) 30vw, 46vw"


def card(podcast: dict, ep: dict, visuals: dict, out_dir: Path) -> str:
    esc = html.escape
    venue, short = venue_of(ep)
    date = datetime.fromisoformat(ep["published"]).strftime("%b %-d")
    derivs = cover_derivatives(ep, podcast, out_dir, "card")
    fallback = f"/img/{ep.get('image') or Path(podcast['image']).name}"
    tag = (f'<a class="venue-tag" href="/venue/{slugify(venue)}/">{esc(venue)}</a>'
           if venue else "")
    alt = ep.get("image_alt") or f"Cover art for {short}"
    return f"""<li class="card reveal" style="--card-accent: {accent_of(ep, visuals)}">
  <div class="card-media">
    {img_tag(derivs, fallback, sizes=CARD_SIZES, cls="cover", alt=alt)}
    <button class="play" aria-pressed="false" aria-label="Play {esc(short)}">{PLAY_ICONS}</button>
    <span class="eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
  </div>
  <div class="card-body">
    <h3 class="title"><a href="/e/{ep['slug']}/">{esc(short)}</a></h3>
    <p class="meta">{tag}<time datetime="{ep['published'][:10]}">{esc(date)}</time>
       <span>{fmt_duration(ep['duration'])}</span></p>
    <div class="wave-slot">{wave_data(podcast, ep, visuals, 96, f"Scrub {short}")}</div>
  </div>
</li>"""


def build_index(podcast: dict, eps: list[dict], visuals: dict, out_dir: Path) -> str:
    esc = html.escape
    hero = eps[0]
    _, hero_title = venue_of(hero)

    hero_derivs = cover_derivatives(hero, podcast, out_dir, "hero")

    years = []
    for year in sorted({e["published"][:4] for e in eps[1:]}, reverse=True):
        cards = [card(podcast, ep, visuals, out_dir)
                 for ep in eps[1:] if ep["published"][:4] == year]
        years.append(f'<section class="year"><h2>{year}<span class="count">'
                     f'{len(cards)} episodes</span></h2>'
                     f'<ul class="episodes">{"".join(cards)}</ul></section>')

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
        hero_venue=(lambda v: f'<a class="venue-tag" href="/venue/{slugify(v)}/">{esc(v)}</a>'
                    if v else "")(venue_of(hero)[0]),
        hero_duration=fmt_duration(hero["duration"]),
        hero_image=img_tag(
            hero_derivs,
            f"/img/{hero.get('image') or Path(podcast['image']).name}",
            sizes="100vw", cls="hero-img", eager=True,
            alt=hero.get("image_alt") or f"Cover art for {hero_title}"),
        hero_wave=wave(podcast, hero, visuals, 200, f"Scrub {hero_title}"),
        years="".join(years),
    )
    return page(podcast, podcast["title"], podcast["description"], body,
                image_url(podcast, Path(podcast["image"]).name),
                path="/",
                head=preload_image(hero_derivs, sizes="100vw"),
                jsonld=(series_jsonld(podcast, eps),))


def build_episode_page(podcast: dict, ep: dict, visuals: dict, out_dir: Path) -> str:
    esc = html.escape
    venue, short = venue_of(ep)
    image = ep.get("image") or Path(podcast["image"]).name
    transcript = load_transcript(ep["slug"])
    trail = [("Home", "/")]
    if venue:
        trail += [("Venues", "/venues/"), (venue, f"/venue/{slugify(venue)}/")]
    trail.append((short, f"/e/{ep['slug']}/"))

    body = render(
        tpl("episode.html"),
        accent=accent_of(ep, visuals),
        transcript=transcript_html(transcript),
        cover=img_tag(cover_derivatives(ep, podcast, out_dir, "card"),
                      f"/img/{image}", sizes="(min-width: 40rem) 10rem, 9rem",
                      cls="cover", eager=True,
                      alt=ep.get("image_alt") or f"Cover art for {short}"),
        title=esc(short),
        date=(f'<time datetime="{ep["published"][:10]}">'
              f'{datetime.fromisoformat(ep["published"]).strftime("%B %-d, %Y")}</time>'),
        venue=(f' — <a href="/venue/{slugify(venue)}/">{esc(venue)}</a>' if venue else ""),
        number=ep.get("episode") or "—",
        wave=wave(podcast, ep, visuals, 240, f"Scrub {short}"),
        duration=fmt_duration(ep["duration"]),
        notes=ep["description"],
        audio=esc(audio_url(podcast, ep, op3=False)),
        size=f"{ep['audio_length'] / 1e6:.0f} MB",
    )
    return page(podcast, f"{short} — {podcast['title']}", ep["description"], body,
                image_url(podcast, image),
                path=f"/e/{ep['slug']}/", og_type="article",
                jsonld=(episode_jsonld(podcast, ep), breadcrumbs(podcast, trail)))


def build_venue_page(podcast: dict, venue: str, eps: list[dict], visuals: dict,
                     out_dir: Path) -> str:
    esc = html.escape
    info = (podcast.get("venues") or {}).get(venue, {})
    path = f"/venue/{slugify(venue)}/"
    listening = sum(e["duration"] for e in eps)
    blurb = info.get("blurb") or (
        f"Episodes covering research published at {info.get('full_name', venue)}. "
        f"Each one works through a single paper: what the authors built, how they "
        f"evaluated it, and what the results support.")

    body = render(
        tpl("venue.html"),
        venue=esc(venue),
        full_name=esc(info.get("full_name", venue)),
        blurb=esc(blurb),
        count=f"{len(eps)} episode{'s' if len(eps) != 1 else ''}",
        listening=f"{listening // 60} minutes of listening",
        link=(f'<p class="venue-link"><a href="{esc(info["url"])}">'
              f'{esc(info.get("full_name", venue))} website</a></p>' if info.get("url") else ""),
        cards="".join(card(podcast, ep, visuals, out_dir) for ep in eps),
    )

    site = podcast["site_url"]
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{venue} episodes",
        "url": site + path,
        "description": blurb,
        "isPartOf": {"@type": "WebSite", "name": podcast["title"], "url": site + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(eps),
            "itemListElement": [
                {"@type": "ListItem", "position": i, "url": f"{site}/e/{ep['slug']}/",
                 "name": venue_of(ep)[1]}
                for i, ep in enumerate(eps, 1)],
        },
    }
    indexable = venue_is_indexable(podcast, venue, eps)
    return page(podcast, f"{venue} — {podcast['title']}", blurb, body,
                image_url(podcast, Path(podcast["image"]).name),
                path=path,
                robots="" if indexable else "noindex,follow",
                jsonld=(collection,
                        breadcrumbs(podcast, [("Home", "/"), ("Venues", "/venues/"),
                                              (venue, path)])))


def build_venues_index(podcast: dict, groups: dict) -> str:
    esc = html.escape
    rows = []
    for venue, eps in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rows.append(
            f'<li><a href="/venue/{slugify(venue)}/">{esc(venue)}</a>'
            f'<span>{len(eps)} episode{"s" if len(eps) != 1 else ""}</span></li>')
    body = (f'<header class="masthead"><h1>Venues</h1>'
            f'<p>Episodes grouped by the conference or journal the paper appeared in.</p>'
            f'</header><ul class="venue-list">{"".join(rows)}</ul>')
    return page(podcast, f"Venues — {podcast['title']}",
                "Episodes grouped by the conference or journal the paper appeared in.",
                body, image_url(podcast, Path(podcast["image"]).name),
                path="/venues/",
                jsonld=(breadcrumbs(podcast, [("Home", "/"), ("Venues", "/venues/")]),))


def build_sitemap(podcast: dict, eps: list[dict], groups: dict) -> str:
    site = podcast["site_url"]
    newest = max(e["published"] for e in eps)[:10]
    urls = [(site + "/", newest), (f"{site}/venues/", newest)]
    urls += [(f"{site}/venue/{slugify(v)}/", max(e["published"] for e in g)[:10])
             for v, g in groups.items() if venue_is_indexable(podcast, v, g)]
    urls += [(f"{site}/e/{e['slug']}/", e["published"][:10]) for e in eps]
    body = "".join(f"  <url><loc>{loc}</loc><lastmod>{mod}</lastmod></url>\n"
                   for loc, mod in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'{body}</urlset>\n')


def build_robots(podcast: dict) -> str:
    # Assistants citing the show is the point, so they are welcome explicitly
    agents = "\n".join(f"User-agent: {a}\nAllow: /\n"
                       for a in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"))
    return (f"User-agent: *\nAllow: /\n\n{agents}\n"
            f"Sitemap: {podcast['site_url']}/sitemap.xml\n")


def build_llms_txt(podcast: dict, eps: list[dict], groups: dict) -> str:
    site = podcast["site_url"]
    out = [f"# {podcast['title']}", "", plain(podcast["description"]), "",
           "> Episodes are AI-generated discussions of published HCI research. Every episode "
           "page links the original paper and its DOI; cite the paper, not the episode.", ""]
    for venue, group in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        out.append(f"## {venue}")
        for ep in group:
            summary = plain(ep["description"]).split(". ")[0][:160]
            out.append(f"- [{ep['title']}]({site}/e/{ep['slug']}/): {summary}. "
                       f"Transcript: {site}/e/{ep['slug']}/transcript.vtt")
        out.append("")
    out += ["## Resources", "",
            f"- Feed: {site}{podcast['feed_path']}",
            f"- Venues: {site}/venues/",
            f"- Sitemap: {site}/sitemap.xml", ""]
    return "\n".join(out)


def build_404(podcast: dict, eps: list[dict], visuals: dict, out_dir: Path) -> str:
    body = ('<header class="masthead"><h1>Page not found</h1>'
            '<p>That link has no episode behind it. The most recent episodes are below, '
            'or browse <a href="/venues/">by venue</a>.</p></header>'
            '<section class="year"><h2>Latest</h2><ul class="episodes">'
            + "".join(card(podcast, ep, visuals, out_dir) for ep in eps[:6])
            + "</ul></section>")
    return page(podcast, f"Page not found — {podcast['title']}",
                "That link has no episode behind it.", body,
                image_url(podcast, Path(podcast["image"]).name),
                path="/404.html", robots="noindex,follow")


def main():
    podcast = load_podcast()
    eps = visible_episodes()
    visuals = load_visuals()

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "img").mkdir(parents=True)

    used_images = {e["image"] for e in eps if e.get("image")} | {Path(podcast["image"]).name}
    for name in used_images:
        # The feed's itunes:image needs the full-size original
        shutil.copy2(ROOT / "images" / name, OUT / "img" / name)

    thumbs = OUT / "img" / "t"
    thumbs.mkdir(parents=True, exist_ok=True)
    if not thumbnails.available():
        print("  Pillow missing — serving full-size covers", file=sys.stderr)

    for asset in ASSETS.iterdir():
        shutil.copy2(asset, OUT / asset.name)

    (OUT / podcast["feed_path"].lstrip("/")).write_text(build_feed(podcast, eps))
    (OUT / "index.html").write_text(build_index(podcast, eps, visuals, thumbs))

    transcribed = 0
    for ep in eps:
        d = OUT / "e" / ep["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(build_episode_page(podcast, ep, visuals, thumbs))
        tr = load_transcript(ep["slug"])
        if tr and tr.get("segments"):
            (d / "transcript.vtt").write_text(vtt(tr))
            (d / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False))
            transcribed += 1

    groups = venue_index(eps)
    for venue, group in groups.items():
        d = OUT / "venue" / slugify(venue)
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(build_venue_page(podcast, venue, group, visuals, thumbs))
    (OUT / "venues").mkdir(exist_ok=True)
    (OUT / "venues" / "index.html").write_text(build_venues_index(podcast, groups))

    (OUT / "sitemap.xml").write_text(build_sitemap(podcast, eps, groups))
    (OUT / "robots.txt").write_text(build_robots(podcast))
    (OUT / "llms.txt").write_text(build_llms_txt(podcast, eps, groups))
    (OUT / "404.html").write_text(build_404(podcast, eps, visuals, thumbs))

    (OUT / "CNAME").write_text(urlparse(podcast["site_url"]).hostname + "\n")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(eps)} episodes, {len(groups)} venue pages, "
          f"{transcribed} transcripts into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
