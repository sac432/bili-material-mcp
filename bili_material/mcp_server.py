"""MCP shell around :class:`bili_material.service.BiliMaterial`.

Only read-only tools are registered. There are deliberately no tools (and no
hidden switches) for commenting, replying, messaging, liking, uploading or
following.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import render
from .client import BiliError
from .service import BiliMaterial

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)

server = MCPServer(
    name="bili-material",
    instructions=(
        "Read-only Bilibili material source. Outputs are compact plain text with an "
        "approximate token count at the end. When you need several videos, pick them "
        "from search results first and read them together with ONE get_video_digests "
        "call (up to 5) instead of separate get_video_digest calls. Page through long "
        "subtitles with get_subtitle(offset=next_offset) only when needed."
    ),
)

_material: BiliMaterial | None = None


def material() -> BiliMaterial:
    global _material
    if _material is None:
        _material = BiliMaterial()
    return _material


def _error(exc: Exception) -> str:
    return f"error: {exc}"


@server.tool(annotations=READ_ONLY, structured_output=False)
async def search_videos(
    keyword: str,
    limit: int = 10,
    order: Literal["totalrank", "click", "pubdate", "dm", "stow", "scores"] = "totalrank",
) -> str:
    """Search Bilibili videos. Returns one line per video: bvid | title | uploader |
    play/like/comment counts | duration | publish date. limit is capped at 20.
    order: totalrank (default), click, pubdate, dm (danmaku), stow (favorites), scores (comments)."""
    try:
        return render.search_text(await material().search_videos(keyword, limit, order))
    except BiliError as exc:
        return _error(exc)


@server.tool(annotations=READ_ONLY, structured_output=False)
async def get_video_digest(
    bvid: str,
    subtitle_max_chars: int = 3000,
    top_comments: int = 25,
) -> str:
    """Digest of ONE video (for several videos use get_video_digests): metadata and stats, compressed subtitle (timestamps
    removed, lines merged; first subtitle_max_chars characters), and the top hot comments
    sorted by likes. bvid may be a BV id or a video URL. If the subtitle is truncated, the
    output gives next_offset for get_subtitle."""
    try:
        return render.digest_text(
            await material().get_video_digest(bvid, subtitle_max_chars, top_comments)
        )
    except BiliError as exc:
        return _error(exc)


@server.tool(annotations=READ_ONLY, structured_output=False)
async def get_video_digests(
    bvids: list[str],
    subtitle_max_chars: int = 20000,
    top_comments: int = 20,
) -> str:
    """Batch digest: metadata, the FULL compressed subtitle (default, up to 20000 chars per
    video) and top hot comments for up to 5 videos in ONE call, so no follow-up
    get_subtitle call is needed. Prefer this over calling get_video_digest repeatedly —
    each extra tool step resends the whole conversation. To only skim videos before
    choosing, pass a small subtitle_max_chars (e.g. 500). subtitle_max_chars and
    top_comments apply per video. A video that fails is reported in its own section without aborting the rest.
    Reading 5 videos can take about 30 seconds because requests are throttled."""
    try:
        return render.digests_text(
            await material().get_video_digests(bvids, subtitle_max_chars, top_comments)
        )
    except BiliError as exc:
        return _error(exc)


@server.tool(annotations=READ_ONLY, structured_output=False)
async def get_subtitle(bvid: str, max_chars: int = 3000, offset: int = 0, page: int = 1) -> str:
    """Read the compressed subtitle of a video in chunks. Start with offset=0 and pass the
    returned next_offset to continue. page selects the part of a multi-part video. Requires login."""
    try:
        return render.subtitle_text(await material().get_subtitle(bvid, max_chars, offset, page))
    except BiliError as exc:
        return _error(exc)


@server.tool(annotations=READ_ONLY, structured_output=False)
async def get_hot_comments(bvid: str, limit: int = 20, max_chars_per_comment: int = 150) -> str:
    """Top comments of a video sorted by likes, with emote codes, duplicates and very short
    comments removed. limit is capped at 50. Anonymous access only returns a few comments."""
    try:
        return render.comments_text(
            await material().get_hot_comments(bvid, limit, max_chars_per_comment)
        )
    except BiliError as exc:
        return _error(exc)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
