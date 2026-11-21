"""Small two-level (memory + JSON file) cache with per-entry TTL."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._mem: dict[str, tuple[float, Any]] = {}

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        return self.directory / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        now = time.time()
        hit = self._mem.get(key)
        if hit and hit[0] > now:
            return hit[1]
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("key") != key or payload.get("expires", 0) <= now:
            return None
        self._mem[key] = (payload["expires"], payload["value"])
        return payload["value"]

    def set(self, key: str, value: Any, ttl: float) -> None:
        expires = time.time() + ttl
        self._mem[key] = (expires, value)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._path(key).write_text(
                json.dumps(
                    {"key": key, "expires": expires, "value": value},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        except OSError:
            pass  # disk cache is best effort
