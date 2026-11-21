"""Runtime configuration, overridable through environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    credential_file: Path
    cache_dir: Path
    min_interval: float  # seconds between two outbound requests
    max_retries: int
    backoff_base: float  # seconds; delay = backoff_base * 2**attempt

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("BILI_DATA_DIR", PROJECT_ROOT / "data"))
        return cls(
            data_dir=data_dir,
            credential_file=Path(
                os.environ.get("BILI_CREDENTIAL_FILE", data_dir / "credential.json")
            ),
            cache_dir=Path(os.environ.get("BILI_CACHE_DIR", data_dir / "cache")),
            min_interval=max(1.0, _env_float("BILI_MIN_INTERVAL", 1.2)),
            max_retries=max(0, _env_int("BILI_MAX_RETRIES", 3)),
            backoff_base=max(0.5, _env_float("BILI_BACKOFF_BASE", 2.0)),
        )


# Cache TTLs in seconds.
TTL_SEARCH = 30 * 60
TTL_INFO = 6 * 3600
TTL_SUBTITLE = 7 * 24 * 3600
TTL_COMMENTS = 2 * 3600
