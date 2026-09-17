"""Environment-driven configuration for the Knowledge Engine.

All values come from environment variables so the module can be run locally,
in tests, and in Docker without code changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = "data/knowledge.db"
DEFAULT_OUTPUT_DIR = "data/output"
DEFAULT_LOG_LEVEL = "INFO"

#: Version of the *extended* Knowledge Pack structure. The approved shared
#: fields (pack_id, source_observation_ids) are unversioned; everything else is
#: provisional until the team signs off, hence the "-provisional" suffix.
SCHEMA_VERSION = "0.2.0-provisional"

#: Fallback scan id used when the caller does not supply one.
DEFAULT_SCAN_ID = "scan_000001"

#: Hard ceiling for journey path length, protects cyclic graphs.
DEFAULT_MAX_JOURNEY_LENGTH = 8

#: Hard ceiling for how many journeys we materialise.
DEFAULT_MAX_JOURNEYS = 200


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings."""

    db_path: Path
    pack_output_dir: Path
    log_level: str
    max_journey_length: int
    max_journeys: int
    media_root: Path

    def ensure_dirs(self) -> None:
        """Create the directories the engine writes into."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.pack_output_dir.mkdir(parents=True, exist_ok=True)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_settings() -> Settings:
    """Read settings from the environment on every call.

    Deliberately not cached: tests override ``KNOWLEDGE_DB_PATH`` per test and
    expect the next call to see the new value.
    """
    return Settings(
        db_path=Path(os.getenv("KNOWLEDGE_DB_PATH", DEFAULT_DB_PATH)),
        pack_output_dir=Path(os.getenv("KNOWLEDGE_PACK_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)),
        log_level=os.getenv("KNOWLEDGE_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        max_journey_length=_int_env("KNOWLEDGE_MAX_JOURNEY_LENGTH", DEFAULT_MAX_JOURNEY_LENGTH),
        max_journeys=_int_env("KNOWLEDGE_MAX_JOURNEYS", DEFAULT_MAX_JOURNEYS),
        media_root=Path(os.getenv("KNOWLEDGE_MEDIA_ROOT", ".")),
    )
