# bili-material-mcp | Read-only, token-efficient Bilibili material MCP

[中文](README.md) | English

> **In three lines**
> - A Bilibili material source for writing agents: **search videos, read subtitles and hot comments**, returned as compact plain text.
> - **Read-only**: there is no code for commenting, messaging, liking or following — it never speaks with your account.
> - **Token-efficient**: summarising 3 videos in dsh takes 2 steps and ~50K tokens, versus ~217K for dsh-bili-scroll ([measurements](docs/BENCHMARK.md), in Chinese).

Unofficial; not affiliated with Bilibili. For personal research and writing reference.

## What it does

- `search_videos`: keyword search, one line per video (BV id, title, uploader, play/like/comment counts, duration, date)
- `get_video_digests`: metadata, **full subtitle** and hot comments for up to 5 videos in **one call / one agent step**
- `get_video_digest` / `get_subtitle` / `get_hot_comments`: single video, subtitle paging, comments only

Subtitles lose timestamps and short lines are merged; comments lose emote codes, duplicates and very short entries. Repeated reads hit a local cache.

## Install

Python 3.10+.

```powershell
git clone https://github.com/sac432/bili-material-mcp.git
cd bili-material-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Login (needed for subtitles)

```powershell
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login
```

Scan the QR code with the Bilibili app (or open `data/login_qrcode.png`). The credential stays in `data/credential.json` on your machine. **Use a secondary account.** Without login, search and metadata work, but there are no subtitles and only ~3 hot comments.

## Connect

**Claude Code**: copy `.mcp.json.example` to `.mcp.json` in your project and replace `<install-dir>`.

**DeepSeek Harness (dsh)**: add this to `~/.dsh/profiles/web/cordis.patch.yml`, then restart dsh:

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

Any MCP client works. From code, skip MCP and use `from bili_material import BiliMaterial`, which returns dicts.

## Guarantees

- Only read tools are registered; there is no write code path and no switch to enable one
- Requests are serialised at least 1.2 s apart with backoff on rate limiting; no site-wide crawling
- The credential stays local; `data/` is git-ignored

## Why it is cheap

Each agent step resends the system prompt, tool definitions and all earlier results, so **the number of steps costs more than the size of any single result**. This server returns several videos in one call, includes the full subtitle so the agent does not come back for the rest, and uses pruned plain text instead of JSON.

## Troubleshooting

- **No subtitles**: check login with `python -m bili_material.login --check`; some videos have none.
- **curl error 77**: caused by a non-ASCII install path with the default curl_cffi client; this project uses aiohttp instead. Open an issue if you still see it.
- **"no SESSDATA" after scanning**: the QR code expired or login was cancelled on the phone; scan again.

## License

GPL-3.0-or-later, because it depends on [bilibili-api-python](https://github.com/Nemo2011/bilibili-api) (GPL-3.0-or-later). Interface usage was informed by adoresever/bilibili-mcp and c1overzz/dsh-bili-scroll (both MIT); no code was copied. Subtitles and comments belong to their authors; use them as reference and quote sparingly with attribution.
