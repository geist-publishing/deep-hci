# HCI Deep Dives — self-hosted

Podcast hosting without Podbean: a static feed and website on GitHub Pages, with
the audio served from GitHub release assets (one release per year, `audio-<year>`).

## Files

| File | Purpose |
|---|---|
| `podcast.yaml` | Channel metadata, repo name, OP3 toggle |
| `episodes.yaml` | One entry per episode. The single source of truth |
| `build.py` | Builds `_site/`: `feed.xml`, `index.html`, `/e/<slug>/`, images |
| `publish_episode.py` | Adds an episode: uploads audio, updates `episodes.yaml`, pushes |
| `upload_audio.py` | One-time bulk upload of `audio/` to the yearly releases |
| `export_from_podbean.py` | One-time export from Podbean (already run) |
| `.github/workflows/pages.yml` | Builds and deploys on push and hourly |

`audio/` and `_site/` are not in git. `audio/` is the local master copy of every
episode — keep it backed up.

## Publishing an episode

```bash
python publish_episode.py --title "CHI 2026 ..." --description notes.html \
    --audio episode.m4a --image cover.jpg [--at 2026-10-01T08:00Z]
```

Without `--at` the episode goes live at the next build. With `--at` in the future
it stays out of the feed until the hourly Action picks it up. That's the piece
that was broken on Podbean: `upload_episode.py` sent `status="draft"`, and Podbean
never publishes drafts, which is why five episodes never went out.

## Preview locally

```bash
python build.py && python -m http.server 8000 -d _site
```

## Switch-over runbook

The feed URL stays `https://www.deep-hci.org/feed.xml`, which Apple, Spotify and
the other directories already use, so **no feed redirect is needed**. Only DNS moves.

1. Create the public repo and push; upload audio with `upload_audio.py`.
2. Enable Pages (Settings → Pages → Source: GitHub Actions) and set the custom
   domain to `www.deep-hci.org`.
3. At Hover, point `www` (CNAME) to `kkai.github.io`, and the apex `deep-hci.org`
   to GitHub's A records: 185.199.108.153, 185.199.109.153, 185.199.110.153,
   185.199.111.153. Then enable "Enforce HTTPS" in the Pages settings.
4. Check `https://www.deep-hci.org/feed.xml` in a validator (podba.se) and
   subscribe in a podcast app.
5. Leave the Podbean account alone for a few weeks as a fallback, then cancel it.

Note: GitHub disables scheduled workflows in public repos after 60 days without
repository activity. Publishing an episode counts as activity; if the show pauses
for longer, re-enable the workflow in the Actions tab.
