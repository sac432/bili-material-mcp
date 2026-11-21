"""Render service dicts as compact plain text for LLM consumption.

Plain text was chosen over JSON because it carries no quotes, braces or
escaped characters, and field names appear once in a header rather than once
per record. Every rendering ends with an approximate token count.
"""

from __future__ import annotations

from .compress import estimate_tokens


def _num(n: int | None) -> str:
    n = int(n or 0)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def with_footer(body: str, cached: bool | None = None) -> str:
    tokens = estimate_tokens(body)
    flags = f" | cache={'hit' if cached else 'miss'}" if cached is not None else ""
    return f"{body}\n[~{tokens} tokens{flags}]"


def search_text(res: dict) -> str:
    lines = [f"search \"{res['keyword']}\" order={res['order']} n={len(res['items'])}"]
    lines.append("# bvid | title | up | play/like/comment | dur | date")
    for it in res["items"]:
        lines.append(
            f"{it['bvid']} | {it['title']} | {it['author']} | "
            f"{_num(it['play'])}/{_num(it['like'])}/{_num(it['comments'])} | "
            f"{it['duration']} | {it['pubdate']}"
        )
    if not res["items"]:
        lines.append("(no results)")
    lines.append("link: https://www.bilibili.com/video/<bvid>")
    return with_footer("\n".join(lines), res.get("cached"))


def meta_lines(m: dict) -> list[str]:
    s = m["stats"]
    lines = [
        f"{m['bvid']} 《{m['title']}》",
        f"up={m['author']}" + (f" zone={m['zone']}" if m.get("zone") else "") + f" date={m['pubdate']} dur={m['duration']} parts={len(m['pages'])}",
        (
            f"view={_num(s['view'])} like={_num(s['like'])} coin={_num(s['coin'])} "
            f"fav={_num(s['favorite'])} reply={_num(s['reply'])} dm={_num(s['danmaku'])} share={_num(s['share'])}"
        ),
    ]
    if m.get("desc"):
        lines.append(f"desc{'(truncated)' if m.get('desc_truncated') else ''}: {m['desc']}")
    lines.append(f"url: {m['url']}")
    return lines


def subtitle_lines(sub: dict) -> list[str]:
    status = sub["status"]
    if status == "login_required":
        return ["[subtitle] unavailable: login required (run `python -m bili_material.login`)"]
    if status == "none":
        return ["[subtitle] none (no uploader or AI subtitle for this video)"]
    head = (
        f"[subtitle] lan={sub['lan']} src={sub['source']} chars={sub['offset']}-"
        f"{sub['offset'] + len(sub['text'])}/{sub['total_chars']}"
    )
    if sub["truncated"]:
        head += f" truncated; next_offset={sub['next_offset']}"
    return [head, sub["text"]]


def comments_lines(c: dict) -> list[str]:
    head = f"[hot comments] {len(c['items'])} shown / {c['total'] or '?'} total, sorted by likes"
    if c.get("clipped"):
        head += f"; {c['clipped']} clipped"
    lines = [head]
    for it in c["items"]:
        extra = f" r{it['replies']}" if it.get("replies") else ""
        lines.append(f"- ({_num(it['like'])}赞{extra}) {it['text']}")
    if c.get("note"):
        lines.append(f"note: {c['note']}")
    return lines


def subtitle_text(sub: dict) -> str:
    head = [f"{sub['bvid']} p{sub.get('page', 1)}"]
    return with_footer("\n".join(head + subtitle_lines(sub)), sub.get("cached"))


def comments_text(c: dict) -> str:
    return with_footer("\n".join([c["bvid"]] + comments_lines(c)), c.get("cached"))


def digest_text(d: dict) -> str:
    lines = meta_lines(d["meta"]) + subtitle_lines(d["subtitle"])
    if d.get("comments") is not None:
        lines += comments_lines(d["comments"])
    cached = d["meta"].get("cached") and d["subtitle"].get("cached", True)
    if d.get("comments") is not None:
        cached = cached and d["comments"].get("cached")
    return with_footer("\n".join(lines), bool(cached))
