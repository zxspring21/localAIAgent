"""Detect and stop repetitive LLM output (common with small MLX models)."""

import logging
import re

logger = logging.getLogger(__name__)

# Stop stream when the same delta repeats this many times in a row
MAX_IDENTICAL_DELTA_STREAK = 8
# Hard cap on stream chunks per completion
MAX_STREAM_CHUNKS = 4096


def normalize_stream_delta(delta: str, collected: str) -> str:
    """Some servers send cumulative text instead of deltas — keep only new tokens."""
    if not delta:
        return ""
    if collected and delta.startswith(collected) and len(delta) > len(collected):
        return delta[len(collected) :]
    return delta


def should_stop_stream(delta: str, last_delta: str, streak: int) -> bool:
    if not delta or len(delta.strip()) == 0:
        return False
    if delta == last_delta and streak >= MAX_IDENTICAL_DELTA_STREAK:
        logger.warning("Stream stopped: identical delta repeated %d times: %r", streak, delta[:80])
        return True
    return False


def collapse_repetition(text: str, min_phrase_len: int = 3, max_repeats: int = 2) -> str:
    """Remove runaway repeated phrases from completed text."""
    if not text or len(text) < min_phrase_len * 3:
        return text

    # Collapse consecutive identical lines
    lines = text.split("\n")
    collapsed_lines: list[str] = []
    repeat_count = 0
    prev = None
    for line in lines:
        if line == prev:
            repeat_count += 1
            if repeat_count <= max_repeats:
                collapsed_lines.append(line)
        else:
            repeat_count = 0
            collapsed_lines.append(line)
            prev = line
    text = "\n".join(collapsed_lines)

    # Collapse short phrase loops at end (e.g. "the the the the")
    words = text.split()
    if len(words) >= 6:
        for n in range(min(8, len(words) // 2), 0, -1):
            tail = words[-n:]
            count = 0
            i = len(words) - n
            while i >= 0 and words[i : i + n] == tail:
                count += 1
                i -= n
            if count >= 4:
                keep = words[: len(words) - n * (count - 1)]
                text = " ".join(keep)
                logger.warning("Collapsed %d repetitions of phrase: %r", count, " ".join(tail))
                break

    # Regex: same sentence repeated 3+ times
    pattern = re.compile(r"(.{10,120}?)(?:\1){2,}", re.DOTALL)
    cleaned, n = pattern.subn(r"\1", text)
    if n:
        logger.warning("Collapsed %d repeated sentence blocks", n)
        return cleaned.strip()

    return text.strip()
