# bili-material-mcp

中文 | [English](README.en.md)

面向自媒体写作的 **只读、省 token** 的 B站素材 MCP server。它可以搜索视频、读取字幕和热门评论，并把结果压缩成紧凑的纯文本交给 Claude Code、DeepSeek Harness（dsh）等 agent 使用。

它包含两部分：

- **核心库** `bili_material.service.BiliMaterial`：返回普通 dict，写作流水线里的节点可以直接 `import` 调用，不经过模型；
- **MCP 外壳** `bili_material.mcp_server`：把同样的数据渲染成紧凑文本，供 agent 调用。

> 非官方项目，与哔哩哔哩无任何关联。仅供个人学习、研究和写作参考，请勿用于商业用途。

## 设计原则

- **只读**：只注册读取类工具，代码里不存在发评论、回复、私信、点赞、投币、收藏、投稿、关注等任何写操作，也没有开关可以打开。
- **按需、少量**：一次一个关键词或几条视频，不做全站爬取和批量抓取用户数据。
- **节流**：所有请求串行排队，间隔至少 1.2 秒（可配置，不低于 1 秒）并带随机抖动；遇到风控码（-412、-352、-799 等）或网络错误时按指数退避重试。
- **省 token**：精简字段、纯文本输出、字幕和评论清洗、本地缓存，并尽量减少 agent 的调用步数（详见下文）。

## 安装

需要 Python 3.10+。

```powershell
git clone https://github.com/sac432/bili-material-mcp.git
cd bili-material-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 登录

```powershell
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login           # 扫码登录
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login --check   # 检查已保存的凭据
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login --logout  # 删除凭据
```

- 二维码会打印在终端里，同时写到 `data/login_qrcode.png`（登录后自动删除），约 3 分钟过期。
- 凭据保存在 `data/credential.json`。`data/` 已加入 `.gitignore`，请勿提交或分享该文件。可用环境变量 `BILI_CREDENTIAL_FILE` 修改位置。
- **强烈建议使用小号。** 即使只读并且做了节流，自动化访问仍有可能触发风控，不要拿主号冒险。

### 不登录能用什么

| 能力 | 匿名 | 登录后 |
|---|---|---|
| 搜索视频 | 可以 | 可以 |
| 视频信息和数据 | 可以 | 可以 |
| 字幕 | **不可以**：播放器接口 `x/player/wbi/v2` 需要 `SESSDATA` | 可以（视频需有 UP主字幕或 AI 字幕） |
| 热门评论 | 只有第一页，通常 **约 3 条** | 每个视频最多 3 页（约 60 条原始评论） |

## 接入 Claude Code

把 `.mcp.json.example` 复制为目标项目里的 `.mcp.json`，并把路径改成你本机的安装位置：

```json
{
  "mcpServers": {
    "bili-material": {
      "type": "stdio",
      "command": "<安装目录>/.venv/Scripts/python.exe",
      "args": ["-X", "utf8", "-m", "bili_material.mcp_server"]
    }
  }
}
```

## 接入 DeepSeek Harness（dsh）

dsh 通过自带的 `@deepseek-ai/dsh-mcp-client` 插件连接 MCP server。在 profile 的 patch 文件（例如 `~/.dsh/profiles/web/cordis.patch.yml`，文件顶层必须是 YAML 数组）里加入：

```yaml
- insert:
    - id: mcp-bili-material
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: bili-material
        transport: stdio
        command: '<安装目录>/.venv/Scripts/python.exe'
        args: ['-X', 'utf8', '-m', 'bili_material.mcp_server']
        cwd: '<安装目录>'
        toolCallTimeoutMs: 90000
```

重启 dsh 后，工具会以 `mcp__bili-material__search_videos` 等名字出现。这是标准 MCP server，不是 dsh 专用插件，同一套代码可以接入任何 MCP 客户端。

## 工具

所有工具都返回紧凑纯文本，末尾附 `[~N tokens | cache=hit|miss]`。`bvid` 可以填 BV 号，也可以填包含 BV 号的视频链接。

| 工具 | 参数（默认值） | 返回 |
|---|---|---|
| `search_videos` | `keyword`，`limit=10`（最多 20），`order=totalrank`（还可选 `click`、`pubdate`、`dm`、`stow`、`scores`） | 每个视频一行：bvid、标题、UP主、播放/点赞/评论数、时长、日期 |
| `get_video_digests` | `bvids`（列表，最多 5 个），`subtitle_max_chars=20000`（即完整字幕），`top_comments=20`（均为每个视频） | **一次调用、一步**读完多个视频的信息、**完整**字幕和热评；只想粗看时可传较小的 `subtitle_max_chars`；单个视频失败只在它自己那一节报错；重复和非法 id 会被去掉 |
| `get_video_digest` | `bvid`，`subtitle_max_chars=3000`，`top_comments=25` | 单个视频的信息、数据、简介（≤300 字）、压缩字幕（截断时给出 `next_offset`）、按点赞排序的热评（每条 ≤120 字） |
| `get_subtitle` | `bvid`，`max_chars=3000`（最多 20000），`offset=0`，`page=1` | 分段读取压缩后的字幕，附 `total_chars` 和 `next_offset` |
| `get_hot_comments` | `bvid`，`limit=20`（最多 50），`max_chars_per_comment=150` | 清洗后按点赞排序的评论，带点赞数和回复数 |

### 作为库使用

```python
import asyncio
from bili_material import BiliMaterial

async def main():
    m = BiliMaterial()
    hits = await m.search_videos("AI写作", limit=5)                       # dict
    bvids = [it["bvid"] for it in hits["items"][:3]]
    digests = await m.get_video_digests(bvids)                            # dict: items[...]

asyncio.run(main())
```

## 工作流程

```
模型 ──调用工具──▶ MCP 客户端（Claude Code / dsh）──stdio──▶ mcp_server.py
                                                              │ 只读工具，渲染成文本
                                                              ▼
                                                         service.py（BiliMaterial）
                                                              │ 清洗、压缩、缓存，返回 dict
                                                              ▼
                                                         client.py（BiliClient）
                                                              │ 凭据、节流、重试
                                                              ▼
                                                    bilibili-api-python ──▶ B站接口
```

以 `get_video_digests` 为例，每个视频依次经过：

1. **视频信息**：查缓存（6 小时），未命中时请求视频信息接口，只保留标题、UP主、日期、时长、7 项数据和截断后的简介。
2. **字幕**：查缓存（7 天），未命中时用登录凭据请求播放器接口，优先选中文 UP主字幕，其次 AI 中文字幕；下载字幕 JSON 并压缩，整份写入缓存后再按需要的长度返回。
3. **热评**：查缓存（2 小时，匿名和登录分开），未命中时按点赞排序拉取评论并清洗、去重、截断。

最后把所有结果渲染成紧凑文本，附上 token 估算返回给模型。

## 省 token 的做法

1. **纯文本而不是 JSON**：字段名只在表头出现一次或写成简短的 `key=value`，没有引号、括号和转义字符；大数字缩写成 `186.9万`。库这一层仍然返回结构化 dict。
2. **精简字段**：搜索结果去掉封面、头像、`<em>` 高亮标签、标签和排名内部字段等约 60 个字段。
3. **字幕压缩**：去掉时间戳、空行和连续重复行；把连续重复的字缩短（`哈哈哈哈哈哈` → `哈哈哈`）；把短句合并成句子和段落（停顿超过 2.5 秒或累计约 160 字时分段）。截断点落在段落或句子边界；剩余部分不超过窗口 25% 时直接一次给完。
4. **评论清洗**：去掉 B站表情码（`[doge]`）、emoji 和「回复 @用户:」前缀；丢弃有效字符少于 4 个的评论；归一化后去重；每条截断；不包含置顶评论（通常是推广）。
5. **截断都有标记**：`desc(truncated)`、`truncated; next_offset=...`、`N clipped`。
6. **默认值保守、有硬上限**：每次调用都有长度和条数上限。
7. **减少步数**：这是效果最大的一项。agent 每多走一步，都要把系统提示、工具定义和之前所有工具结果重新发送一遍，所以步数比单次返回的大小更重要。`get_video_digests` 一次就把多个视频的信息、完整字幕和热评全部取回。
8. **本地缓存**（`data/cache/`，内存加 JSON 文件）：搜索 30 分钟、视频信息 6 小时、字幕 7 天、评论 2 小时。同一个视频重复读取不会再发请求。
9. **每次返回附 token 估算**：中日韩字符按 1 token、其他字符按 4 个算 1 token 估算；真实分词器有差异，只适合横向比较。

## 实测数据

**在 dsh 里的真实账单**：dsh 0.2.2-rc.5，DeepSeek-V4.1-Flash，2026-11-20。每次都用同一句提示，总结 BV1RNidYCEdq、BV1g2tB6YERy、BV1cNWd6DEgY 三个视频的字幕要点和热评观点，只在提示里限制可用的工具。数字取自 dsh 会话日志，把每次请求的用量相加。

| 工具 | 第几次 | 步数 | 总 token | 未缓存输入 | 缓存输入 | 输出 |
|---|---|---:|---:|---:|---:|---:|
| `get_video_digests`（完整字幕，当前默认） | 1 | 2 | 51544 | 23886 | 22144 | 5514 |
| `get_video_digests`（完整字幕，当前默认） | 2 | 2 | 50049 | 13717 | 32256 | 4076 |
| `get_video_digests`（每个视频 2500 字字幕） | 1 | 3 | 76941 | 30042 | 43136 | 3763 |
| `get_video_digests`（每个视频 2500 字字幕） | 2 | 3 | 77627 | 13880 | 57984 | 5763 |
| `get_video_digest`（单个视频） | 1 | 4 | 115433 | 22205 | 86528 | 6700 |
| `get_video_digest`（单个视频） | 2 | 4 | 119282 | 18746 | 91008 | 9528 |
| dsh-bili-scroll 的 `bili_subtitle` + `bili_comments` | 1 | 7 | 217137 | 33086 | 179712 | 4339 |

- 使用当前默认的批量工具，只需要 2 步、1 次工具调用，总量约为单视频版的 43%、dsh-bili-scroll 的 23%。
- 节省主要来自步数减少：缓存输入随步数快速增长。由于缓存命中的价格远低于未命中，实际费用的差距会小于 token 总数的差距。
- 每种配置只跑了 1 到 2 次，样本很小；模型会自己决定参数和策略，单次结果会有波动。
- 有一次运行恰好在 MCP 重启后，前缀缓存还没有建立，所以它的未缓存输入偏高。

更多数据（与原始 API 返回大小的对比、与 dsh-bili-scroll 工具输出的逐项对比、原始数据的来源构成）见 [README.en.md](README.en.md#measured-comparison)。可用以下命令复现与原始 API 的对比：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\compare_tokens.py "AI写作" --videos 3
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `BILI_DATA_DIR` | `./data` | 凭据和缓存的根目录 |
| `BILI_CREDENTIAL_FILE` | `$BILI_DATA_DIR/credential.json` | 登录凭据 |
| `BILI_CACHE_DIR` | `$BILI_DATA_DIR/cache` | 缓存目录 |
| `BILI_MIN_INTERVAL` | `1.2` | 请求间隔秒数（最低 1.0） |
| `BILI_MAX_RETRIES` | `3` | 风控或网络错误时的重试次数 |
| `BILI_BACKOFF_BASE` | `2.0` | 退避秒数，每次重试翻倍 |

## 目录结构

```text
bili_material/
  client.py      只读的原始接口调用、凭据、节流、重试
  service.py     BiliMaterial：清洗压缩和缓存，返回 dict（代码里直接 import 这个）
  compress.py    字幕和评论清洗、分页、token 估算
  render.py      dict 转紧凑文本
  cache.py       内存加 JSON 文件缓存
  mcp_server.py  MCP 外壳（只注册只读工具）
  login.py       扫码登录命令行
scripts/compare_tokens.py
```

## 已知限制

- 字幕需要登录，而且很多视频既没有 UP主字幕也没有 AI 字幕，这时会显示 `[subtitle] none`。
- 有报告称 B站播放器接口偶尔会返回其他视频的 AI 字幕。本工具不做检测，请对照标题核实。
- bilibili-api 17.4.2 的 `QrCodeLogin` 显示登录成功，但保存的 cookie 全为空。本项目的 `bili_material.login` 自己轮询网页扫码接口，同时读取 `Set-Cookie` 和跳转 URL，拿不到 `SESSDATA` 时拒绝保存。
- 在 Windows 上，如果安装路径包含非 ASCII 字符，bilibili-api 默认的 `curl_cffi` 客户端无法加载 CA 证书（curl error 77），因此本项目改用 `aiohttp` 客户端。
- digest 只读取多 P 视频的第一个分 P；其他分 P 用 `get_subtitle(page=N)`。
- 节流按进程计算。同时运行多个 server 实例时，总请求频率会成倍增加。
- 不包含楼中楼回复。
- 批量工具默认返回完整字幕，一次读 5 个长视频可能有数万 token；只想粗看时请调小 `subtitle_max_chars`。

## 许可证与合规

- **bilibili-api-python**（Nemo2011/bilibili-api）使用 **GPL-3.0-or-later** 许可证。本项目依赖它，因此同样以 **GPL-3.0-or-later** 发布，再分发时需遵守 GPL 的要求。
- 接口用法参考了 `adoresever/bilibili-mcp`（MIT）和 `c1overzz/dsh-bili-scroll`（MIT），未复制其代码。
- `mcp`（Python SDK）为 MIT 许可证，`aiohttp` 为 Apache-2.0 许可证。
- 请遵守哔哩哔哩用户协议，尊重 UP主和评论者的著作权：获取的字幕和评论只作写作参考，引用时适量并注明出处，不要整体转载。
- 本工具不会在平台上发布任何内容。
