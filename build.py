#!/usr/bin/env python3
"""
Build the static site into _site/: feed.xml, index.html, one page per episode
(at /e/<slug>/, the same URLs Podbean used), images and CNAME.

Episodes marked `draft: true` or dated in the future are left out, so a daily
rebuild (see .github/workflows/pages.yml) releases scheduled episodes.
"""

import email.utils
import html
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from episodes_io import ROOT, load_episodes, load_podcast, release_tag

OUT = ROOT / "_site"


def audio_url(podcast: dict, ep: dict) -> str:
    url = (f"https://github.com/{podcast['github_repo']}/releases/download/"
           f"{release_tag(ep)}/{ep['audio_file']}")
    if podcast.get("op3"):
        url = "https://op3.dev/e/" + url.removeprefix("https://")
    return url


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


CSS = """
:root { --bg:#fbfaf7; --fg:#1d1d1f; --muted:#6b6b70; --line:#e4e2dc; --accent:#b4441f; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141414; --fg:#ececec; --muted:#9a9a9f; --line:#2c2c2c; --accent:#f08a5d; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font: 17px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; }
a { color: var(--accent); }
header.show { display:flex; gap:20px; align-items:center; margin-bottom:32px; }
header.show img { width:120px; height:120px; border-radius:12px; flex:none; }
header.show h1 { margin:0 0 4px; font-size:28px; }
.muted { color: var(--muted); font-size: 14px; }
.intro { margin: 0 0 32px; }
ol.episodes { list-style:none; padding:0; margin:0; }
ol.episodes li { display:flex; gap:16px; padding:18px 0; border-top:1px solid var(--line); }
ol.episodes img { width:72px; height:72px; border-radius:8px; object-fit:cover; flex:none; }
ol.episodes h2 { font-size:17px; margin:0 0 4px; line-height:1.35; }
ol.episodes h2 a { color: inherit; text-decoration: none; }
ol.episodes h2 a:hover { text-decoration: underline; }
article img.cover { width:100%; max-width:360px; border-radius:12px; }
article h1 { font-size: 26px; line-height: 1.3; }
audio { width:100%; margin: 16px 0; }
@media (max-width: 520px) { header.show { flex-direction: column; align-items: flex-start; } }
"""


def page(podcast: dict, title: str, body: str) -> str:
    esc = html.escape
    return f"""<!doctype html>
<html lang="{podcast['language']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="alternate" type="application/rss+xml" title="{esc(podcast['title'])}" href="{podcast['feed_path']}">
<link rel="icon" href="/img/{Path(podcast['image']).name}">
<link rel="stylesheet" href="/style.css">
</head>
<body><main>
{body}
</main></body>
</html>
"""


def build_index(podcast: dict, eps: list[dict]) -> str:
    esc = html.escape
    rows = []
    for ep in eps:
        date = datetime.fromisoformat(ep["published"]).strftime("%b %d, %Y")
        rows.append(f"""<li>
  <img src="/img/{ep.get('image') or Path(podcast['image']).name}" alt="" loading="lazy">
  <div><h2><a href="/e/{ep['slug']}/">{esc(ep['title'])}</a></h2>
  <div class="muted">{date} · {fmt_duration(ep['duration'])}</div></div>
</li>""")
    body = f"""<header class="show">
  <img src="/img/{Path(podcast['image']).name}" alt="">
  <div><h1>{esc(podcast['title'])}</h1>
  <div class="muted">{esc(podcast['author'])} · <a href="{podcast['feed_path']}">RSS feed</a></div></div>
</header>
<p class="intro">{esc(podcast['description'])}</p>
<ol class="episodes">
{chr(10).join(rows)}
</ol>"""
    return page(podcast, podcast["title"], body)


def build_episode_page(podcast: dict, ep: dict) -> str:
    esc = html.escape
    date = datetime.fromisoformat(ep["published"]).strftime("%B %d, %Y")
    direct = audio_url(podcast, ep)
    body = f"""<p class="muted"><a href="/">← {esc(podcast['title'])}</a></p>
<article>
  <img class="cover" src="/img/{ep.get('image') or Path(podcast['image']).name}" alt="">
  <h1>{esc(ep['title'])}</h1>
  <div class="muted">{date} · {fmt_duration(ep['duration'])} · <a href="{esc(direct)}">Download</a></div>
  <audio controls preload="none" src="{esc(direct)}"></audio>
  {ep['description']}
</article>"""
    return page(podcast, f"{ep['title']} | {podcast['title']}", body)


def main():
    podcast = load_podcast()
    eps = visible_episodes()

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "img").mkdir(parents=True)

    used_images = {e["image"] for e in eps if e.get("image")} | {Path(podcast["image"]).name}
    for name in used_images:
        shutil.copy2(ROOT / "images" / name, OUT / "img" / name)

    (OUT / podcast["feed_path"].lstrip("/")).write_text(build_feed(podcast, eps))
    (OUT / "index.html").write_text(build_index(podcast, eps))
    (OUT / "style.css").write_text(CSS)
    for ep in eps:
        d = OUT / "e" / ep["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(build_episode_page(podcast, ep))

    (OUT / "CNAME").write_text(urlparse(podcast["site_url"]).hostname + "\n")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(eps)} episodes into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
