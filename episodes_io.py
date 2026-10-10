"""Read/write episodes.yaml, podcast.yaml and visuals.json."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
EPISODES_FILE = ROOT / "episodes.yaml"
PODCAST_FILE = ROOT / "podcast.yaml"
VISUALS_FILE = ROOT / "visuals.json"


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_representer)


def load_podcast() -> dict:
    return yaml.safe_load(PODCAST_FILE.read_text())


def load_episodes() -> list[dict]:
    if not EPISODES_FILE.exists():
        return []
    return yaml.safe_load(EPISODES_FILE.read_text()) or []


def save_episodes(episodes: list[dict]):
    # Drop empty keys so the file stays tidy
    cleaned = [{k: v for k, v in ep.items() if v is not None} for ep in episodes]
    EPISODES_FILE.write_text(
        yaml.dump(cleaned, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)
    )


def load_visuals() -> dict:
    """Waveform peaks and accent colours, keyed by episode guid."""
    if not VISUALS_FILE.exists():
        return {}
    return json.loads(VISUALS_FILE.read_text())


def save_visuals(data: dict):
    # sort_keys keeps diffs readable when an episode is added
    VISUALS_FILE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def release_tag(episode: dict) -> str:
    return f"audio-{episode['published'][:4]}"


def audio_path(episode: dict) -> Path:
    return ROOT / "audio" / episode["published"][:4] / episode["audio_file"]


def transcript_path(slug: str) -> Path:
    return ROOT / "transcripts" / f"{slug}.json"


def load_transcript(slug: str) -> dict | None:
    """None when an episode hasn't been transcribed; every caller degrades."""
    path = transcript_path(slug)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
