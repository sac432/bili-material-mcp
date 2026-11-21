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
        "approximate token count at the end. Prefer get_video_digest (one call for "
        "metadata + subtitle + hot comments); page through long subtitles with "
        "get_subtitle(offset=next_offset) only when needed."
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
    top_comments: int = 10,
) -> str:
    """One-call digest of a video: metadata and stats, compressed subtitle (timestamps
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
