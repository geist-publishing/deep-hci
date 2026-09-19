"""Read/write episodes.yaml and podcast.yaml, with readable multi-line HTML."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent
EPISODES_FILE = ROOT / "episodes.yaml"
PODCAST_FILE = ROOT / "podcast.yaml"


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


def release_tag(episode: dict) -> str:
    return f"audio-{episode['published'][:4]}"
