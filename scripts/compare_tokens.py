"""Compare raw Bilibili API payload size with bili-material MCP output size.

For one keyword, takes the first N search results and measures, per video:
  raw  = JSON of every raw API response an agent would otherwise read
         (video info + player info + subtitle body + one hot-comment page)
  mcp  = text returned by get_video_digest with default parameters
plus the search call itself. Sizes are in characters and approximate tokens
(see bili_material.compress.estimate_tokens).

Usage:
    python scripts/compare_tokens.py "AI写作" --videos 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from bili_material import BiliMaterial, render
from bili_material.client import LoginRequired
from bili_material.compress import estimate_tokens
from bili_material.service import ORDERS


def size(obj: object) -> tuple[int, int]:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return len(text), estimate_tokens(text)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("--videos", type=int, default=3)
    ap.add_argument("--search-limit", type=int, default=10)
    args = ap.parse_args()

    m = BiliMaterial()
    c = m.client
    rows = []

    raw_search = await c.search_videos_raw(args.keyword, args.search_limit, ORDERS["totalrank"])
    raw_search_items = raw_search.get("result") or []
    mcp_search = render.search_text(await m.search_videos(args.keyword, args.search_limit))
    rows.append(("search", f'"{args.keyword}" x{args.search_limit}', size(raw_search_items), size(mcp_search)))

    for item in (await m.search_videos(args.keyword, args.search_limit))["items"][: args.videos]:
        bvid = item["bvid"]
        raw_parts = []
        info = await c.video_info_raw(bvid)
        raw_parts.append(info)
        try:
            player = await c.player_info_raw(bvid, info["cid"])
            raw_parts.append(player)
            tracks = [t for t in (player.get("subtitle") or {}).get("subtitles") or [] if t.get("subtitle_url")]
            if tracks:
                raw_parts.append(await c.subtitle_body_raw(tracks[0]["subtitle_url"]))
        except LoginRequired:
            pass
        raw_parts.append(await c.comments_page_raw(info["aid"]))
        digest = render.digest_text(await m.get_video_digest(bvid))
        rows.append(("digest", bvid, size(raw_parts), size(digest)))

    print(f"| call | target | raw chars | raw ~tokens | mcp chars | mcp ~tokens | ratio |")
    print("|---|---|---:|---:|---:|---:|---:|")
    tot_raw = tot_mcp = 0
    for kind, target, (rc, rt), (mc, mt) in rows:
        tot_raw += rt
        tot_mcp += mt
        print(f"| {kind} | {target} | {rc} | {rt} | {mc} | {mt} | {mt / rt:.1%} |")
    print(f"| **total** | | | {tot_raw} | | {tot_mcp} | {tot_mcp / tot_raw:.1%} |")
    print(f"\nlogged_in={m.logged_in} requests={c.request_count}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
