# bili-material-mcp

[中文](README.md) | English

A **read-only, token-efficient** Bilibili material source for a self-media writing
pipeline. It ships as:

- an importable core library (`bili_material.service.BiliMaterial`, returns plain dicts) for
  pipeline nodes that call it directly from code, and
- a thin MCP server (`bili_material.mcp_server`) that renders the same data as compact text
  for agents such as Claude Code.

It exists as a low-cost, read-only alternative to agent-style Bilibili plugins that resend
full context on every step and can post comments with the user's account.

## Scope and guarantees

- **Read-only.** Only five read tools are registered. There are no tools, code paths or
  switches for commenting, replying, private messages, liking, coins, favorites, uploading or
  following.
- **On demand, small volume.** One keyword search or one video at a time. No site-wide
  crawling, no batch user scraping.
- **Throttled.** All outbound requests are serialised with a minimum interval of 1.2 s
  (configurable, never below 1 s), plus jitter, with exponential-backoff retries on
  rate-limit / risk-control codes (-412, -352, -799, ...) and network errors.

## Installation

Requires Python 3.10+.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Login

```powershell
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login           # scan QR code
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login --check   # verify saved credential
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login --logout  # delete it
```

- The QR code is printed in the terminal and also written to `data/login_qrcode.png`
  (deleted after login). It expires after about 3 minutes.
- The credential is saved to `data/credential.json`. `data/` is in `.gitignore`; never commit
  or share this file. Override the location with `BILI_CREDENTIAL_FILE`.
- **Use a secondary account.** Automated access, even read-only and throttled, can trigger
  risk control; do not risk your main account.

### What works without login

| Capability | Anonymous | Logged in |
|---|---|---|
| `search_videos` | yes | yes |
| Video metadata / stats | yes | yes |
| Subtitles | **no** – `x/player/wbi/v2` requires `SESSDATA` (enforced by bilibili-api and by Bilibili, which returns no subtitle URLs anonymously) | yes, when the video has uploader or AI subtitles |
| Hot comments | first page only, typically **~3 comments** | up to 3 pages (~60 raw comments) per video |

## Using it in Claude Code

Copy `.mcp.json.example` to `.mcp.json` in the project where you want the tools (adjust the
interpreter path if the repository lives elsewhere):

```json
{
  "mcpServers": {
    "bili-material": {
      "type": "stdio",
      "command": "<install-dir>/.venv/Scripts/python.exe",
      "args": ["-X", "utf8", "-m", "bili_material.mcp_server"]
    }
  }
}
```

## Using it in DeepSeek Harness (dsh)

dsh connects to MCP servers through its `@deepseek-ai/dsh-mcp-client` plugin. Add an
`insert` entry to the profile patch layer, e.g. `~/.dsh/profiles/web/cordis.patch.yml`
(the file must stay a top-level YAML array):

```yaml
- insert:
    - id: mcp-bili-material
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: bili-material
        transport: stdio
        command: '<install-dir>/.venv/Scripts/python.exe'
        args: ['-X', 'utf8', '-m', 'bili_material.mcp_server']
        cwd: '<install-dir>'
        toolCallTimeoutMs: 90000
```

Restart dsh; the tools appear as `mcp__bili-material__search_videos` and so on. This is a
plain MCP server, not a dsh-specific plugin, so the same process serves Claude Code, dsh and
any other MCP client.

## Tools

All tools return compact plain text ending with `[~N tokens | cache=hit|miss]`.
`bvid` accepts a BV id or any URL containing one.

| Tool | Parameters (defaults) | Returns |
|---|---|---|
| `search_videos` | `keyword`, `limit=10` (max 20), `order=totalrank` (`click`, `pubdate`, `dm`, `stow`, `scores`) | one line per video: bvid, title, uploader, play/like/comment counts, duration, date |
| `get_video_digest` | `bvid`, `subtitle_max_chars=3000`, `top_comments=25` | metadata + stats + description (≤300 chars), compressed subtitle (first chunk, with `next_offset` when truncated), top comments by likes (≤120 chars each) — **one call instead of four** |
| `get_video_digests` | `bvids` (list, max 5), `subtitle_max_chars=20000` (full subtitle), `top_comments=20` (per video) | the same digest with the **full** subtitle for several videos in **one call / one agent step**; pass a small `subtitle_max_chars` to skim; a failing video is reported in its own section; duplicates and invalid ids are dropped |
| `get_subtitle` | `bvid`, `max_chars=3000` (max 20000), `offset=0`, `page=1` | one chunk of the compressed subtitle, `total_chars`, `next_offset` |
| `get_hot_comments` | `bvid`, `limit=20` (max 50), `max_chars_per_comment=150` | cleaned comments sorted by likes, with like and reply counts |

Library usage (for future pipeline nodes):

```python
import asyncio
from bili_material import BiliMaterial

async def main():
    m = BiliMaterial()
    hits = await m.search_videos("AI写作", limit=5)          # dict
    digest = await m.get_video_digest(hits["items"][0]["bvid"])  # dict: meta / subtitle / comments

asyncio.run(main())
```

## Token-saving strategy

1. **Output format: compact plain text, not JSON.** Field names appear once in a header line
   (search) or as short `key=value` pairs; there are no quotes, braces or escape sequences, and
   large counts are shortened (`186.9万`). The library layer still returns structured dicts,
   so code consumers lose nothing.
2. **Field pruning.** Search drops cover URLs, avatars, HTML `<em>` highlight tags, tags,
   ranking internals and about 60 other fields; digest keeps only title, uploader, zone, date,
   duration, part count, seven stats, a clipped description and the URL.
3. **Subtitle compression.** Timestamps removed; empty and consecutive duplicate lines removed;
   runs of repeated characters collapsed (`哈哈哈哈哈哈` → `哈哈哈`); short lines merged into
   sentences and paragraphs (new paragraph on pauses > 2.5 s or after ~160 chars). The first
   chunk is cut at a paragraph or sentence boundary, and the rest can be paged with
   `offset`.
4. **Comment cleaning.** Bilibili emote codes (`[doge]`), Unicode emoji and `回复 @user:`
   prefixes removed; comments shorter than 4 meaningful characters dropped; duplicates removed
   after normalisation; each comment clipped; pinned comments (often promotions) excluded.
5. **Explicit truncation markers.** Every clipped field says so (`desc(truncated)`,
   `truncated; next_offset=...`, `N clipped`).
6. **Conservative defaults and hard caps.** Subtitle 3000 chars per call (cap 20000), digest
   25 comments, comments 20 (cap 50), search 10 (cap 20).
7. **Fewer round trips.** `get_video_digest` returns metadata, subtitle and comments together,
   and `get_video_digests` does that for up to five videos in a single tool call. In an agent
   loop every extra step resends the system prompt, tool definitions and all earlier results,
   so the number of steps matters more than the size of any single result. A subtitle whose
   remaining text is within 25% of the window is returned whole rather than leaving a short
   tail that would need another call.
8. **Local cache** (`data/cache/`, memory + JSON files): search 30 min, video info 6 h,
   subtitles 7 days, comments 2 h. A repeated call for the same bvid makes no network request.
9. **Token estimate on every response** so the agent (and you) can see the cost. The estimate
   counts 1 token per CJK character and 1 per 4 other characters; real tokenizers differ, so
   use it for relative comparisons.

## Measured comparison

`scripts/compare_tokens.py` takes the first N videos for a keyword and compares the raw API
responses an agent would otherwise read (video info + player info + subtitle body + one
hot-comment page; for search, the raw result list) with this server's output at default
parameters.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\compare_tokens.py "AI写作" --videos 3
```

Keyword `AI写作`, 2026-11-20, **anonymous** (no subtitles, first comment page only):

| call | target | raw chars | raw ~tokens | mcp chars | mcp ~tokens | ratio |
|---|---|---:|---:|---:|---:|---:|
| search | "AI写作" x10 | 15326 | 4635 | 1101 | 504 | 10.9% |
| digest | BV1acxv6SEpp | 49924 | 13470 | 682 | 323 | 2.4% |
| digest | BV17ysv64EKC | 28053 | 7443 | 538 | 211 | 2.8% |
| digest | BV1RNidYCEdq | 26348 | 7280 | 645 | 300 | 4.1% |
| **total** | | | 32828 | | 1338 | 4.1% |

Same keyword and videos, **logged in** (subtitles included, all three videos have AI
subtitles; up to 3 comment pages). These runs used the earlier digest default of 10 comments;
the default is now 25:

| call | target | raw chars | raw ~tokens | mcp chars | mcp ~tokens | ratio |
|---|---|---:|---:|---:|---:|---:|
| search | "AI写作" x10 | 15326 | 4635 | 1100 | 503 | 10.9% |
| digest | BV1acxv6SEpp | 167461 | 45663 | 3011 | 2432 | 5.3% |
| digest | BV17ysv64EKC | 144052 | 41539 | 3499 | 3133 | 7.5% |
| digest | BV1RNidYCEdq | 160119 | 45869 | 3957 | 3322 | 7.2% |
| **total** | | | 137706 | | 9390 | 6.8% |

Where the raw size comes from (BV17ysv64EKC, single requests):

| raw response | chars | ~tokens | useful content |
|---|---:|---:|---|
| video info | 2538 | 712 | title, owner, stats, description |
| player info | 3399 | 870 | subtitle track list |
| subtitle body | 56835 | 18675 | 576 segments, 6065 chars of actual text |
| one hot-comment page | 81284 | 21283 | 18 comments (avatars, decorations, jump links, ...) |

How to read these numbers:

- Most of the saving comes from dropping JSON structure, timestamps and comment metadata, and
  from the default 3000-char subtitle window. The compressed subtitle **text itself is not
  shorter**: the full compressed subtitle of BV17ysv64EKC is 6670 chars versus 6065 raw text
  chars, because punctuation and paragraph breaks are added to unpunctuated AI subtitles.
- Reading the rest of a long subtitle with `get_subtitle(offset=...)` costs roughly one token
  per Chinese character; that part is not reduced further.
- A repeated digest or subtitle page for the same bvid is served from cache with zero network
  requests.
- Measured 2026-11-20 with bilibili-api-python 17.4.2; counts drift as videos gain views and
  comments.

### Compared with the dsh-bili-scroll MCP

The raw-API numbers above are an upper bound. `dsh-bili-scroll` (v2.5.2) already prunes fields
in its vendored `bilibili-mcp`, so it was also measured directly: same keyword, same three
videos, logged in, its four read tools enabled via `BILI_MCP_TOOLS`. Its workflow needs
`bili_search` + per video `bili_video_info`, `bili_subtitle`, `bili_comments` (10 calls); this
server needs `search_videos` + one `get_video_digest` per video (4 calls).

| setup | calls | tool-result ~tokens | cumulative input ~tokens* |
|---|---:|---:|---:|
| dsh-bili-scroll, 30 comments (its default) | 10 | 26076 | 147205 |
| dsh-bili-scroll, 10 comments | 10 | 20168 | 122346 |
| bili-material, 3000-char subtitle, 10 comments (earlier default) | 4 | 9390 | 33896 |
| bili-material, full subtitle + 30 comments | 4 | 18268 | 48896 |

\* Sum of input tokens over a sequential agent loop in which every request resends the previous
tool results plus a nominal 3000-token system prompt; excludes the model's own outputs and
reasoning. This models the "resend the whole context on every step" cost and is an estimate,
not a billing measurement.

Observations:

- With equal content (full subtitles, 30 comments), tool results are about 30% smaller. The
  savings are in search (−60%: no aid, raw timestamps or descriptions) and comments (no rpid,
  user names, timestamps, emote codes or duplicates). Subtitles are slightly **larger** here
  because punctuation and paragraph breaks are added.
- Most of the difference in total cost comes from fewer round trips (4 vs 10 calls), which
  shrinks the resent context.
- dsh-bili-scroll includes two sub-replies per comment, which this server omits; they can be
  useful writing material.

### End-to-end in dsh (billed usage)

Measured in dsh 0.2.2-rc.5 with DeepSeek-V4.1-Flash on 2026-11-20. Same prompt for every run:
summarise the subtitles and hot comments of BV1RNidYCEdq, BV1g2tB6YERy and BV1cNWd6DEgY, with
the allowed tool set restricted in the prompt. Numbers are dsh's per-request usage summed over
the run (from the session log).

| tools | run | steps | total tok | uncached in | cached in | output |
|---|---|---:|---:|---:|---:|---:|
| `get_video_digests` (batch) | 1 | 3 | 76941 | 30042 | 43136 | 3763 |
| `get_video_digests` (batch) | 2 | 3 | 77627 | 13880 | 57984 | 5763 |
| `get_video_digests` (batch, full subtitles by default) | 1 | 2 | 51544 | 23886 | 22144 | 5514 |
| `get_video_digests` (batch, full subtitles by default) | 2 | 2 | 50049 | 13717 | 32256 | 4076 |
| `get_video_digest` (single) | 1 | 4 | 115433 | 22205 | 86528 | 6700 |
| `get_video_digest` (single) | 2 | 4 | 119282 | 18746 | 91008 | 9528 |
| dsh-bili-scroll `bili_subtitle` + `bili_comments` | 1 | 7 | 217137 | 33086 | 179712 | 4339 |

- The batch tool saved one step versus single digests (the model already parallelised the
  three single calls) and about a third of total tokens. dsh-bili-scroll's run called one tool
  per step and used about 2.8× the batch total.
- In every bili-material run the model fetched the rest of each subtitle with `get_subtitle`
  in a second tool step: for a "summarise the video" task it wants the whole subtitle.
- After making the batch tool return full subtitles by default, both runs finished in two
  steps with a single tool call and no follow-up, about 35% below the 2500-char batch runs.
  The first of them followed an MCP restart (changed tool list), so its cache was cold.
- Batch run 1 was the first request after a dsh restart, so its prefix cache was cold; that
  explains its higher uncached input.
- Two runs per configuration (one for dsh-bili-scroll) is a small sample; the model chooses
  its own parameters and strategy, so individual runs vary.

Example `search_videos` output:

```text
search "AI写作" order=totalrank n=3
# bvid | title | up | play/like/comment | dur | date
BV1acxv6SEpp | 热门AI文本模型写小说从夯到拉锐评！五级作者评测AI写小说等级！ | -星月凌云- | 7.6万/1074/551 | 5:13 | 2026-10-30
BV17ysv64EKC | 真实采访用Ai写网文月稿费10万+的作者，公开Ai写小说创作流程 | -星月凌云- | 3270/138/65 | 19:34 | 2026-11-19
BV1RNidYCEdq | 【进阶教程】一套连招，彻底释放AI的写作能力 | 檀东东Tango | 186.9万/2.2万/391 | 15:09 | 2024-12-05
link: https://www.bilibili.com/video/<bvid>
[~168 tokens | cache=miss]
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BILI_DATA_DIR` | `./data` | credential and cache root |
| `BILI_CREDENTIAL_FILE` | `$BILI_DATA_DIR/credential.json` | saved login |
| `BILI_CACHE_DIR` | `$BILI_DATA_DIR/cache` | response cache |
| `BILI_MIN_INTERVAL` | `1.2` | seconds between requests (minimum 1.0) |
| `BILI_MAX_RETRIES` | `3` | retries on rate-limit / network errors |
| `BILI_BACKOFF_BASE` | `2.0` | backoff seconds, doubled per attempt |

## Project layout

```text
bili_material/
  client.py      raw read-only API calls, credential, throttle, retry
  service.py     BiliMaterial: compaction + cache, returns dicts (import this from code)
  compress.py    subtitle/comment cleaning, paging, token estimate
  render.py      dict -> compact text
  cache.py       memory + JSON file cache
  mcp_server.py  MCP shell (read-only tools only)
  login.py       QR-code login CLI
scripts/compare_tokens.py
```

## Known limitations

- Subtitles require login, and many videos have neither uploader nor AI subtitles; the digest
  then reports `[subtitle] none`.
- Bilibili's player API has been reported to occasionally return an AI subtitle belonging to
  a different video. This tool does not detect that; sanity-check subtitles against the title.
- bilibili-api 17.4.2's `QrCodeLogin` reports success but stores empty cookies (it only
  parses the redirect URL in a way that no longer matches). `bili_material.login` therefore
  polls the web QR endpoints itself, reads both `Set-Cookie` and the redirect URL, and refuses
  to save a credential without `SESSDATA`.
- On Windows, bilibili-api's default `curl_cffi` client cannot load its CA bundle when the
  install path contains non-ASCII characters (curl error 77). This project selects the
  `aiohttp` client instead.
- Only the first part of a multi-part video is used by the digest; use `get_subtitle(page=N)`
  for other parts.
- Throttling is per process. Running several server instances multiplies the request rate.

## Licensing and compliance

- **bilibili-api-python** (Nemo2011/bilibili-api) is licensed **GPL-3.0-or-later** (verified
  from the installed 17.4.2 wheel's `LICENSE` file and PyPI classifier; GitHub's license
  detection does not show it). Because this project imports it, this project is released
  under **GPL-3.0-or-later** as well. If you redistribute it, GPL obligations apply.
- Interface usage was informed by `adoresever/bilibili-mcp` (MIT) and
  `c1overzz/dsh-bili-scroll` (MIT); no code was copied from either.
- `mcp` (Python SDK) is MIT; `aiohttp` is Apache-2.0.
- Intended for personal, non-commercial research and writing reference. Respect Bilibili's
  terms of service and the copyright of creators and commenters: use retrieved subtitles and
  comments as reference material, quote sparingly with attribution, and do not republish them
  wholesale.
- The tool never posts anything on the platform.
