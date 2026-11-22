from __future__ import annotations

import re


# Только пробелы/табы — не трогаем переносы строк (абзацы)
_SENTENCE_END = re.compile(r"([.!?…]+)([ \t]*)([«\"'(\[]?)([a-zа-яё])", re.IGNORECASE)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.:;!?…»\")\]])")
_SPACE_AFTER_OPEN = re.compile(r"([«\"'(\[])\s+")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NL = re.compile(r"\n{3,}")
_MISSING_SPACE_AFTER_PUNCT = re.compile(r"([,.:;!?…])([А-Яа-яЁёA-Za-z«\"'])")
_DASH_SPACING = re.compile(r"\s*[—–-]\s*")


def format_russian_transcript(text: str, paragraph_breaks: bool = True) -> str:
    """Сделать транскрипт удобно читаемым: пунктуация, пробелы, регистр."""
    if not text or not text.strip():
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = _MULTI_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = _MISSING_SPACE_AFTER_PUNCT.sub(r"\1 \2", text)
    text = _DASH_SPACING.sub(" — ", text)

    # Заглавная буква после конца предложения
    def _capitalize_match(match: re.Match[str]) -> str:
        end, _spaces, open_q, letter = match.groups()
        return f"{end} {open_q}{letter.upper()}"

    text = _SENTENCE_END.sub(_capitalize_match, text)

    # Первая буква текста
    for i, ch in enumerate(text):
        if ch.isalpha():
            text = text[:i] + ch.upper() + text[i + 1 :]
            break

    if paragraph_breaks:
        # Разбиваем длинный поток на абзацы по концам предложений (~3–5 фраз)
        sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
        paragraphs: list[str] = []
        bucket: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            bucket.append(sentence)
            if len(bucket) >= 4:
                paragraphs.append(" ".join(bucket))
                bucket = []
        if bucket:
            paragraphs.append(" ".join(bucket))
        text = "\n\n".join(paragraphs)

    text = _MULTI_NL.sub("\n\n", text)
    return text.strip() + "\n"


def segments_to_plain_text(segments: list[dict], paragraph_gap_sec: float = 1.4) -> str:
    """Склеить сегменты Whisper в текст с абзацами по длинным паузам."""
    parts: list[str] = []
    paragraph: list[str] = []
    prev_end: float | None = None

    for seg in segments:
        piece = (seg.get("text") or "").strip()
        if not piece:
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        if prev_end is not None and start - prev_end >= paragraph_gap_sec and paragraph:
            parts.append(" ".join(paragraph))
            paragraph = []
        paragraph.append(piece)
        prev_end = end

    if paragraph:
        parts.append(" ".join(paragraph))

    raw = "\n\n".join(parts)
    return format_russian_transcript(raw, paragraph_breaks=False)


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    index = 1
    for seg in segments:
        text = format_russian_transcript((seg.get("text") or "").strip(), paragraph_breaks=False).strip()
        if not text:
            continue
        start = format_timestamp(float(seg.get("start") or 0.0))
        end = format_timestamp(float(seg.get("end") or 0.0))
        lines.append(str(index))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        index += 1
    return "\n".join(lines)