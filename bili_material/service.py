"""High-level, read-only material API.

Every public coroutine returns a plain ``dict`` so it can be used directly by
pipeline nodes; :mod:`bili_material.render` turns those dicts into the compact
text served over MCP.
"""

from __future__ import annotations

import re
import time
from typing import Any

from bilibili_api import search

from .cache import Cache
from .client import BiliClient, BiliError, LoginRequired
from .compress import (
    clean_comment,
    clip,
    comment_key,
    compress_subtitle,
    one_line,
    page_text,
    strip_html,
)
from .config import TTL_COMMENTS, TTL_INFO, TTL_SEARCH, TTL_SUBTITLE, Settings

_BVID = re.compile(r"BV[0-9A-Za-z]{10}")

ORDERS = {
    "totalrank": search.OrderVideo.TOTALRANK,
    "click": search.OrderVideo.CLICK,
    "pubdate": search.OrderVideo.PUBDATE,
    "dm": search.OrderVideo.DM,
    "stow": search.OrderVideo.STOW,
    "scores": search.OrderVideo.SCORES,
}

# Hard caps so that a single call can never balloon.
MAX_SEARCH = 20
MAX_COMMENTS = 50
MAX_COMMENT_PAGES = 3
MAX_SUBTITLE_CHARS = 20000


def normalize_bvid(value: str) -> str:
    m = _BVID.search(value or "")
    if not m:
        raise BiliError(f"not a valid BV id or video URL: {value!r}")
    return m.group(0)


def _date(ts: int | None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""


def _clock(text: str) -> str:
    """Normalise search durations such as "15:9" to "15:09"."""
    parts = str(text or "").split(":")
    if not all(x.isdigit() for x in parts):
        return str(text or "")
    secs = 0
    for x in parts:
        secs = secs * 60 + int(x)
    return _duration(secs)


def _duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class BiliMaterial:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.client = BiliClient(self.settings)
        self.cache = Cache(self.settings.cache_dir)

    @property
    def logged_in(self) -> bool:
        return self.client.logged_in

    # ----------------------------------------------------------------- search

    async def search_videos(self, keyword: str, limit: int = 10, order: str = "totalrank") -> dict:
        keyword = one_line(keyword)
        if not keyword:
            raise BiliError("keyword must not be empty")
        limit = max(1, min(int(limit), MAX_SEARCH))
        order_key = order if order in ORDERS else "totalrank"
        key = f"search:{order_key}:{limit}:{keyword}"
        cached = self.cache.get(key)
        if cached is not None:
            return {**cached, "cached": True}

        # Over-fetch slightly: some entries may be non-video results.
        raw = await self.client.search_videos_raw(keyword, min(limit + 5, 42), ORDERS[order_key])
        items = []
        for r in raw.get("result") or []:
            if r.get("type") != "video" or not r.get("bvid"):
                continue
            items.append(
                {
                    "bvid": r["bvid"],
                    "title": one_line(strip_html(r.get("title", ""))),
                    "author": r.get("author", ""),
                    "play": r.get("play", 0),
                    "like": r.get("like", 0),
                    "comments": r.get("review", 0),
                    "duration": _clock(r.get("duration", "")),
                    "pubdate": _date(r.get("pubdate")),
                    "url": f"https://www.bilibili.com/video/{r['bvid']}",
                }
            )
            if len(items) >= limit:
                break
        result = {"keyword": keyword, "order": order_key, "items": items}
        self.cache.set(key, result, TTL_SEARCH)
        return {**result, "cached": False}

    # ------------------------------------------------------------- video info

    async def video_meta(self, bvid: str, desc_max_chars: int = 300) -> dict:
        bvid = normalize_bvid(bvid)
        key = f"info:{bvid}"
        meta = self.cache.get(key)
        cached = meta is not None
        if meta is None:
            info = await self.client.video_info_raw(bvid)
            stat = info.get("stat") or {}
            meta = {
                "bvid": bvid,
                "aid": info.get("aid"),
                "title": one_line(info.get("title", "")),
                "author": (info.get("owner") or {}).get("name", ""),
                "zone": info.get("tname_v2") or info.get("tname", ""),
                "pubdate": _date(info.get("pubdate")),
                "duration": _duration(info.get("duration")),
                "pages": [
                    {"page": p.get("page"), "cid": p.get("cid"), "part": p.get("part", "")}
                    for p in info.get("pages") or []
                ],
                "desc": (info.get("desc") or "").strip(),
                "stats": {
                    "view": stat.get("view", 0),
                    "like": stat.get("like", 0),
                    "coin": stat.get("coin", 0),
                    "favorite": stat.get("favorite", 0),
                    "reply": stat.get("reply", 0),
                    "danmaku": stat.get("danmaku", 0),
                    "share": stat.get("share", 0),
                },
                "url": f"https://www.bilibili.com/video/{bvid}",
            }
            self.cache.set(key, meta, TTL_INFO)
        desc, desc_trunc = clip(one_line(meta["desc"]), desc_max_chars)
        return {**meta, "desc": desc, "desc_truncated": desc_trunc, "cached": cached}

    # --------------------------------------------------------------- subtitle

    async def _subtitle_doc(self, bvid: str, page: int) -> dict:
        """Full compressed subtitle for one part, cached. Never truncated."""
        key = f"subtitle:{bvid}:{page}"
        doc = self.cache.get(key)
        if doc is not None:
            return {**doc, "cached": True}

        meta = await self.video_meta(bvid)
        pages = meta["pages"]
        if not pages:
            raise BiliError("video has no playable parts")
        if page < 1 or page > len(pages):
            raise BiliError(f"page must be between 1 and {len(pages)}")
        cid = pages[page - 1]["cid"]

        player = await self.client.player_info_raw(bvid, cid)
        tracks = ((player.get("subtitle") or {}).get("subtitles")) or []
        tracks = [t for t in tracks if t.get("subtitle_url")]
        if not tracks:
            doc = {"status": "none", "lan": "", "source": "", "text": "", "segments": 0}
            # Absence can be temporary (AI subtitles are generated lazily): short TTL.
            self.cache.set(key, doc, TTL_COMMENTS)
            return {**doc, "cached": False}

        def rank(t: dict) -> tuple[int, int]:
            lan = (t.get("lan") or "").lower()
            is_ai = lan.startswith("ai-") or bool(t.get("ai_type"))
            is_zh = "zh" in lan
            return (0 if is_zh else 1, 1 if is_ai else 0)

        track = sorted(tracks, key=rank)[0]
        body = await self.client.subtitle_body_raw(track["subtitle_url"])
        segments = body.get("body") or []
        lan = track.get("lan", "")
        doc = {
            "status": "ok",
            "lan": lan,
            "source": "ai" if lan.lower().startswith("ai-") or track.get("ai_type") else "uploader",
            "text": compress_subtitle(segments),
            "segments": len(segments),
            "raw_chars": sum(len(str(s.get("content", ""))) for s in segments),
        }
        self.cache.set(key, doc, TTL_SUBTITLE)
        return {**doc, "cached": False}

    async def get_subtitle(
        self, bvid: str, max_chars: int = 3000, offset: int = 0, page: int = 1
    ) -> dict:
        bvid = normalize_bvid(bvid)
        max_chars = max(200, min(int(max_chars), MAX_SUBTITLE_CHARS))
        try:
            doc = await self._subtitle_doc(bvid, int(page))
        except LoginRequired as exc:
            return {"bvid": bvid, "status": "login_required", "message": str(exc)}
        out = {
            "bvid": bvid,
            "page": page,
            "status": doc["status"],
            "lan": doc["lan"],
            "source": doc["source"],
            "cached": doc["cached"],
        }
        if doc["status"] != "ok":
            return out
        text = doc["text"]
        chunk, next_offset = page_text(text, int(offset), max_chars)
        out.update(
            text=chunk,
            offset=max(0, int(offset)),
            next_offset=next_offset,
            total_chars=len(text),
            truncated=next_offset is not None,
        )
        return out

    # --------------------------------------------------------------- comments

    async def _comment_pool(self, bvid: str, want: int) -> dict:
        meta = await self.video_meta(bvid)
        key = f"comments:{bvid}:{'auth' if self.logged_in else 'anon'}"
        pool = self.cache.get(key) or {
            "items": [],
            "seen": [],
            "offset": "",
            "exhausted": False,
            "pages": 0,
            "total": None,
        }
        cached = bool(pool["pages"])
        seen = set(pool["seen"])
        fetched = False
        max_pages = MAX_COMMENT_PAGES if self.logged_in else 1
        while len(pool["items"]) < want and not pool["exhausted"] and pool["pages"] < max_pages:
            raw = await self.client.comments_page_raw(meta["aid"], pool["offset"])
            fetched = True
            pool["pages"] += 1
            cursor = raw.get("cursor") or {}
            pool["total"] = cursor.get("all_count", pool["total"])
            for r in raw.get("replies") or []:
                text = clean_comment((r.get("content") or {}).get("message", ""))
                k = comment_key(text)
                if len(k) < 4 or k in seen:
                    continue
                seen.add(k)
                pool["items"].append(
                    {"like": r.get("like", 0), "replies": r.get("rcount", 0), "text": text}
                )
            next_offset = ((cursor.get("pagination_reply") or {}).get("next_offset")) or ""
            pool["offset"] = next_offset
            if cursor.get("is_end") or not next_offset:
                pool["exhausted"] = True
        if fetched:
            pool["seen"] = list(seen)
            self.cache.set(key, pool, TTL_COMMENTS)
        return {**pool, "cached": cached and not fetched}

    async def get_hot_comments(
        self, bvid: str, limit: int = 20, max_chars_per_comment: int = 150
    ) -> dict:
        bvid = normalize_bvid(bvid)
        limit = max(1, min(int(limit), MAX_COMMENTS))
        max_chars = max(30, int(max_chars_per_comment))
        pool = await self._comment_pool(bvid, limit)
        items = sorted(pool["items"], key=lambda c: c["like"], reverse=True)[:limit]
        out_items = []
        clipped = 0
        for c in items:
            text, t = clip(c["text"], max_chars)
            clipped += t
            out_items.append({**c, "text": text})
        note = ""
        if not self.logged_in and len(items) < limit:
            note = "anonymous access returns only the first few hot comments; log in for more"
        return {
            "bvid": bvid,
            "total": pool["total"],
            "items": out_items,
            "clipped": clipped,
            "note": note,
            "cached": pool["cached"],
        }

    # ----------------------------------------------------------------- digest

    async def get_video_digest(
        self,
        bvid: str,
        subtitle_max_chars: int = 3000,
        top_comments: int = 10,
        max_chars_per_comment: int = 120,
    ) -> dict:
        meta = await self.video_meta(bvid)
        sub = await self.get_subtitle(meta["bvid"], max_chars=subtitle_max_chars)
        comments: dict[str, Any] | None = None
        if top_comments > 0:
            comments = await self.get_hot_comments(meta["bvid"], top_comments, max_chars_per_comment)
        return {"meta": meta, "subtitle": sub, "comments": comments}
