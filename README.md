# HCI Deep Dives — self-hosted

Podcast hosting without Podbean. Two repos:

- **`geist-publishing/deep-hci`** (this one) — the generator, the episode data and
  the website, published to GitHub Pages at <https://www.deep-hci.org>.
- **`geist-publishing/deep-hci-audio`** — the audio, as one release per year
  (`audio-2024`, `audio-2025`, …). Nothing but a README lives in its git tree.

The feed stays at `https://www.deep-hci.org/feed.xml` with its original GUIDs, so
Apple, Spotify and every existing subscriber carry on uninterrupted.

## Files

| File | Purpose |
|---|---|
| `podcast.yaml` | Channel metadata, the two repo names, subscribe links, OP3 toggle |
| `episodes.yaml` | One entry per episode. The single source of truth |
| `visuals.json` | Waveform peaks and accent colours, keyed by guid. Generated, committed |
| `build.py` | Builds `_site/`: `feed.xml`, `index.html`, `/e/<slug>/`, assets, images |
| `build_visuals.py` | Extracts waveforms (ffmpeg) and accents (Pillow). Local only |
| `publish_episode.py` | Adds an episode: uploads audio, updates the data, commits, pushes |
| `upload_audio.py` | One-time bulk upload of `audio/` to the yearly releases |
| `export_from_podbean.py` | One-time export from Podbean (already run) |
| `assets/`, `templates/` | The site's CSS, player and HTML templates |

`audio/` and `_site/` are not in git. **`audio/` is the local master copy of every
episode — keep it backed up.**

## Publishing an episode

```bash
python publish_episode.py --title "CHI 2026 ..." --description notes.html \
    --audio episode.m4a --image cover.jpg [--at 2026-10-01T08:00Z]
```

Without `--at` the episode goes live at the next build. With `--at` in the future it
stays out of the feed until the hourly Action picks it up. This is the thing that was
broken on Podbean: the old `upload_episode.py` sent `status="draft"`, and Podbean never
publishes drafts, which is why five episodes never went out.

## Preview locally

```bash
python build_visuals.py        # only needed after adding episodes
python build.py && python -m http.server 8000 -d _site
```

Note that Python's built-in server ignores Range requests, so seeking in the player
won't work against it. That's a limitation of the test server, not the player — GitHub's
asset host supports Range.

## The design

The waveform is the interface: every episode's strip is drawn from its real audio and
doubles as the scrubber. Each episode's accent colour is sampled from its own cover art
and checked for 4.5:1 contrast on both themes. Type is Geist, with Source Serif 4 for
the show notes. Motion respects `prefers-reduced-motion`.

Because GitHub serves release assets without CORS headers, the player never touches
WebAudio — `createMediaElementSource()` on cross-origin media mutes the element. All
waveform animation is driven by `currentTime`.

## Switch-over runbook

1. Create both public repos in the `geist-publishing` org.
2. Push this repo; run `python upload_audio.py` to push the audio (555 MB) to the
   yearly releases in `deep-hci-audio`.
3. In `deep-hci`: Settings → Pages → Source "GitHub Actions", custom domain
   `www.deep-hci.org`.
4. At Hover, change exactly two records — leave `MX` and the `google-site-verification`
   TXT alone:
   - `www` CNAME → `geist-publishing.github.io`
   - apex `deep-hci.org` A → 185.199.108.153, 185.199.109.153, 185.199.110.153,
     185.199.111.153
   Lower the TTL to 300 a day ahead so a rollback is quick.
5. Wait for the certificate, then enable "Enforce HTTPS". Validate the feed at
   podba.se and subscribe in a podcast app.
6. Keep Podbean paid through the cutover — both feeds stay valid during propagation —
   then cancel it.

GitHub disables scheduled workflows in public repos after 60 days without activity.
Publishing counts as activity; if the show pauses longer, re-enable it in the Actions tab.
