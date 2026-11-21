"""Low-level, read-only access to Bilibili through bilibili-api-python.

Responsibilities: credential loading, request throttling, retry with backoff,
and returning *raw* API payloads. All compaction happens in ``service.py``.

Only read endpoints are wrapped here. Do not add write operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Awaitable, Callable, TypeVar

import aiohttp
from bilibili_api import Credential, comment, request_settings, search, select_client, video
from bilibili_api.exceptions import (
    CredentialNoSessdataException,
    NetworkException,
    ResponseCodeException,
)

from .config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T")

# curl_cffi (the library default) cannot load its CA bundle from a non-ASCII
# path on Windows, so use aiohttp, which bilibili-api also supports.
select_client("aiohttp")
request_settings.set_timeout(15.0)

# Codes that indicate rate limiting / risk control and are worth retrying.
RETRYABLE_CODES = {-412, -352, -351, -509, -799, -500, -503}

CREDENTIAL_FIELDS = ("sessdata", "bili_jct", "buvid3", "buvid4", "dedeuserid", "ac_time_value")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class BiliError(RuntimeError):
    """Readable error raised to callers (and shown to the agent)."""


class LoginRequired(BiliError):
    pass


def load_credential(settings: Settings) -> Credential | None:
    path = settings.credential_file
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("cannot read credential file %s: %s", path, exc)
        return None
    fields = {k: data.get(k) for k in CREDENTIAL_FIELDS if data.get(k)}
    if not fields.get("sessdata"):
        return None
    return Credential(**fields)


def save_credential(settings: Settings, credential: Credential) -> None:
    settings.credential_file.parent.mkdir(parents=True, exist_ok=True)
    data = {k: getattr(credential, k, None) for k in CREDENTIAL_FIELDS}
    data["saved_at"] = int(time.time())
    settings.credential_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Throttle:
    """Serialises outbound requests and enforces a minimum interval."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def __aenter__(self) -> None:
        await self._lock.acquire()
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait + random.uniform(0, 0.3))

    async def __aexit__(self, *exc: object) -> None:
        self._last = time.monotonic()
        self._lock.release()


class BiliClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.credential = load_credential(self.settings)
        self.throttle = Throttle(self.settings.min_interval)
        self.request_count = 0

    @property
    def logged_in(self) -> bool:
        return self.credential is not None

    async def _call(self, what: str, fn: Callable[[], Awaitable[T]]) -> T:
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                async with self.throttle:
                    self.request_count += 1
                    return await fn()
            except CredentialNoSessdataException as exc:
                raise LoginRequired(
                    f"{what}: this endpoint requires login. Run `python -m bili_material.login` first."
                ) from exc
            except ResponseCodeException as exc:
                if exc.code in RETRYABLE_CODES and attempt + 1 < attempts:
                    delay = self.settings.backoff_base * 2**attempt
                    log.warning("%s: code %s, retry in %.1fs", what, exc.code, delay)
                    await asyncio.sleep(delay)
                    continue
                if exc.code == -101:
                    raise LoginRequired(f"{what}: credential is missing or expired (code -101).") from exc
                raise BiliError(f"{what}: Bilibili returned code {exc.code} ({exc.msg}).") from exc
            except (NetworkException, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt + 1 < attempts:
                    delay = self.settings.backoff_base * 2**attempt
                    log.warning("%s: network error %r, retry in %.1fs", what, exc, delay)
                    await asyncio.sleep(delay)
                    continue
                raise BiliError(f"{what}: network error after {attempts} attempts: {exc!r}") from exc
        raise BiliError(f"{what}: exhausted retries")  # pragma: no cover

    # ------------------------------------------------------------------ reads

    async def search_videos_raw(self, keyword: str, page_size: int, order: search.OrderVideo) -> dict:
        return await self._call(
            "search",
            lambda: search.search_by_type(
                keyword,
                search_type=search.SearchObjectType.VIDEO,
                order_type=order,
                page=1,
                page_size=page_size,
            ),
        )

    async def video_info_raw(self, bvid: str) -> dict:
        v = video.Video(bvid=bvid, credential=self.credential)
        return await self._call("video info", v.get_info)

    async def player_info_raw(self, bvid: str, cid: int) -> dict:
        if not self.credential:
            raise LoginRequired(
                "subtitle: Bilibili's player API (x/player/wbi/v2) requires login. "
                "Run `python -m bili_material.login` first."
            )
        v = video.Video(bvid=bvid, credential=self.credential)
        return await self._call("player info", lambda: v.get_player_info(cid=cid))

    async def subtitle_body_raw(self, url: str) -> dict:
        if url.startswith("//"):
            url = "https:" + url

        async def fetch() -> dict:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
                async with s.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)

        return await self._call("subtitle body", fetch)

    async def comments_page_raw(self, aid: int, offset: str = "") -> dict:
        return await self._call(
            "comments",
            lambda: comment.get_comments_lazy(
                aid,
                comment.CommentResourceType.VIDEO,
                offset=offset,
                order=comment.OrderType.LIKE,
                credential=self.credential,
            ),
        )


def run(coro: Awaitable[Any]) -> Any:
    """Convenience for synchronous callers."""
    return asyncio.run(coro)  # type: ignore[arg-type]
