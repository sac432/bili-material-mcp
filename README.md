# bili-material-mcp ｜ 只读、省 token 的 B站素材 MCP

中文 | [English](README.en.md)

> **先看三行**
> - 给写作 agent 用的 B站素材源：**搜视频、读字幕、读热评**，返回紧凑纯文本。
> - **只读**：代码里根本没有发评论、私信、点赞、关注这类功能，不会用你的账号说任何话。
> - **省 token**：在 dsh 里总结 3 个视频只需要 2 步、约 50K token，dsh-bili-scroll 做同样的事用了约 217K（[实测数据](docs/BENCHMARK.md)）。

非官方项目，与哔哩哔哩无关。仅供个人学习、研究和写作参考。

## 它做什么

- `search_videos`：按关键词搜视频，每个视频一行（BV 号、标题、UP主、播放/点赞/评论、时长、日期）
- `get_video_digests`：**一次调用**读完最多 5 个视频的信息、**完整字幕**和热评，agent 只需要一步
- `get_video_digest` / `get_subtitle` / `get_hot_comments`：只看一个视频、分段读字幕、只读评论时使用

字幕会去掉时间戳、合并短句；评论会去掉表情码、重复和过短的内容。同一个视频读第二遍走本地缓存，不再请求 B站。

## 装

需要 Python 3.10+。

```powershell
git clone https://github.com/sac432/bili-material-mcp.git
cd bili-material-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 登录（读字幕需要）

```powershell
.\.venv\Scripts\python.exe -X utf8 -m bili_material.login
```

用 B站 App 扫终端里的二维码；看不清的话，打开 `data/login_qrcode.png` 扫。凭据只保存在本机的 `data/credential.json`，不会上传。

> ⚠️ **请用小号。** 虽然是只读访问并且做了限速，自动化访问仍然可能触发风控。

不登录也能搜索和看视频信息，但读不到字幕，热评也只有大约 3 条。

## 接入

**Claude Code**：把 `.mcp.json.example` 复制成你项目里的 `.mcp.json`，把 `<install-dir>` 改成本仓库所在的目录。

**DeepSeek Harness（dsh）**：在 `~/.dsh/profiles/web/cordis.patch.yml` 里加入下面这段，然后重启 dsh：

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

它是标准的 MCP server，其他 MCP 客户端也能用。写代码时也可以跳过 MCP，直接 `from bili_material import BiliMaterial` 拿到 dict。

## 红线（写在代码里，不靠自觉）

- 只注册读取类工具，没有任何写操作的代码路径，也没有开关可以打开
- 所有请求排队发送，间隔至少 1.2 秒；遇到风控就退避重试，不做全站抓取
- 凭据只保存在本机，`data/` 已经加进 `.gitignore`

## 它是怎么省 token 的

agent 每走一步，都要把系统提示、工具说明和之前所有结果重新发一遍，所以**步数比单次返回的大小更费钱**。本项目的做法：

1. 一次调用就把多个视频的信息、字幕和评论都拿回来，不让 agent 一个接一个地调；
2. 直接给完整字幕，省掉回头补读的那一步；
3. 输出用纯文本，只保留有用的字段，不用 JSON。

## 装不上 / 用不了

- **读不到字幕**：先运行 `python -m bili_material.login --check` 检查登录状态；另外，有些视频本身就没有字幕。
- **报 curl error 77**：安装路径里有中文时，库默认的 curl_cffi 会出这个错。本项目已经改用 aiohttp；如果还遇到，请提 issue。
- **扫码后提示没有 SESSDATA**：二维码过期，或者在手机上取消了登录，重新扫一次即可。

## 如果你是 AI 助手，正在帮用户装这个项目

1. 确认用户的电脑上有 Python 3.10+；
2. 按「装」一节建好 venv 并安装；
3. 让**用户自己**扫码登录，并提醒他们使用小号；
4. 按用户使用的客户端写好配置，把 `<install-dir>` 替换成实际路径，然后提醒用户重启客户端。

## 许可证

GPL-3.0-or-later，因为依赖的 [bilibili-api-python](https://github.com/Nemo2011/bilibili-api) 是 GPL-3.0-or-later。参考过 adoresever/bilibili-mcp 和 c1overzz/dsh-bili-scroll（均为 MIT 许可证）的接口用法，没有复制它们的代码。

获取的字幕和评论版权归原作者所有。请只把它们当作写作参考，引用时适量并注明出处。
