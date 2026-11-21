"""Text compaction helpers: subtitles, comments, truncation and token estimates."""

from __future__ import annotations

import html
import re
from typing import Iterable

_CJK = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿＀-￯]")
_HTML_TAG = re.compile(r"<[^>]+>")
_BILI_EMOTE = re.compile(r"\[[^\[\]\s]{1,12}\]")  # e.g. [doge] [笑哭] [星星眼_2]
_UNICODE_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "‍️⭐⭕〰〽"
    "]+"
)
_REPLY_PREFIX = re.compile(r"^回复\s*@[^:：\s]+\s*[:：]\s*")
_WS = re.compile(r"\s+")
_SENT_END = "。！？!?…~～"
_REPEAT_CHARS = re.compile(r"(.)\1{4,}")  # 哈哈哈哈哈哈 -> 哈哈哈


def estimate_tokens(text: str) -> int:
    """Rough token estimate for mixed Chinese/English text.

    Counts one token per CJK character and one per four other characters. Real
    tokenizers differ (often 0.6-1.5 tokens per Chinese character), so treat the
    number as an order-of-magnitude guide for comparing payload sizes.
    """
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def strip_html(text: str) -> str:
    return html.unescape(_HTML_TAG.sub("", text or ""))


def clip(text: str, limit: int) -> tuple[str, bool]:
    """Truncate to ``limit`` characters; returns (text, truncated)."""
    text = text or ""
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[: max(0, limit - 1)].rstrip() + "…", True


def one_line(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


# ---------------------------------------------------------------------------
# Subtitles
# ---------------------------------------------------------------------------

def compress_subtitle(
    segments: Iterable[dict],
    paragraph_gap: float = 2.5,
    paragraph_chars: int = 160,
) -> str:
    """Turn timestamped subtitle segments into compact paragraphs.

    - drops timestamps
    - removes empty and consecutive duplicate lines
    - merges short lines into sentences (joined by "，" when the line has no
      terminal punctuation)
    - starts a new paragraph on a long pause or once a paragraph is long enough
    """
    paragraphs: list[str] = []
    buf: list[str] = []
    buf_len = 0
    prev_text = ""
    prev_end: float | None = None

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            para = "".join(buf).rstrip("，,、 ")
            if para and para[-1] not in _SENT_END:
                para += "。"
            paragraphs.append(para)
        buf, buf_len = [], 0

    for seg in segments:
        text = one_line(str(seg.get("content", "")))
        text = _REPEAT_CHARS.sub(r"\1\1\1", text)
        if not text or text == prev_text:
            continue
        start = float(seg.get("from", 0) or 0)
        if prev_end is not None and start - prev_end > paragraph_gap and buf_len > 40:
            flush()
        prev_text = text
        prev_end = float(seg.get("to", start) or start)
        if text[-1] not in _SENT_END + "，,、；;：:":
            text += "，"
        buf.append(text)
        buf_len += len(text)
        if buf_len >= paragraph_chars and text[-1] in _SENT_END + "，,":
            flush()
    flush()
    return "\n".join(paragraphs)


def page_text(text: str, offset: int, max_chars: int) -> tuple[str, int | None]:
    """Return a slice of ``text`` starting at ``offset``.

    The cut is moved back to the nearest paragraph or sentence boundary when one
    exists in the last 20% of the window. Returns (chunk, next_offset or None).
    """
    offset = max(0, min(offset, len(text)))
    end = offset + max_chars
    if end >= len(text):
        return text[offset:], None
    window = text[offset:end]
    floor = int(len(window) * 0.8)
    cut = -1
    for marks in ("\n", "。！？!?", "，,"):
        cut = max(window.rfind(m) for m in marks)
        if cut >= floor:
            break
    if cut < floor:
        cut = len(window) - 1
    chunk = window[: cut + 1]
    return chunk.rstrip("\n"), offset + len(chunk)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def clean_comment(text: str) -> str:
    text = _REPLY_PREFIX.sub("", text or "")
    text = _BILI_EMOTE.sub("", text)
    text = _UNICODE_EMOJI.sub("", text)
    text = _REPEAT_CHARS.sub(r"\1\1\1", text)
    return one_line(text)


def comment_key(text: str) -> str:
    """Normalisation used for de-duplication."""
    return re.sub(r"[\W_]+", "", text.lower())[:60]
