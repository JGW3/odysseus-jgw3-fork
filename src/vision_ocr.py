"""OCR on every image, then a short describe-only prompt (experimental, fork only).

RapidOCR reads an image's text locally in about a second, with no tokens and
no GPU, so it runs on every image the vision path sees. The vision model then
only describes the image (and where any text is); the OCR text is attached
verbatim. A thinking model no longer spends its token cap transcribing, and
an image still yields its text when no vision model is available.
ODYSSEUS_OCR_FIRST=0 turns this off and restores the full describe prompt.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
from pathlib import Path
from typing import Optional

from src.constants import VISION_DESCRIBE_PROMPT

logger = logging.getLogger(__name__)

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-first")
_MIN_CHARS = 3
_MAX_PROMPT_CHARS = 4000
# Stricter than the engine's 0.5 default: on photographed pages, lines scored
# 0.5-0.7 were stray fragments (diagram labels, edges of other sheets), never
# real text. Misreads can score higher, which the prompt warns about.
_MIN_CONFIDENCE = 0.7
OCR_MODEL_LABEL = "RapidOCR"

DESCRIBE_WITH_TEXT_PROMPT = (
    "Describe this image: a one or two sentence overview, a blank line, then "
    "the details. Say what any text is and where; if it is short, like a sign "
    "or a label, say what it says. Don't copy out longer text such as a recipe "
    "or a page; just say what it is. OCR text, attached after your "
    "description; it can be wrong, so trust the image:\n<<<\n{ocr}\n>>>"
)
DESCRIBE_NO_TEXT_PROMPT = (
    "Describe this image: a one or two sentence overview, a blank line, then "
    "the details."
)


def _enabled() -> bool:
    return os.getenv("ODYSSEUS_OCR_FIRST", "1").strip().lower() not in {"0", "false", "no", "off"}


def _timeout() -> float:
    try:
        return max(0.5, float(os.getenv("ODYSSEUS_OCR_FIRST_TIMEOUT", "20")))
    except ValueError:
        return 20.0


def _read(path: str) -> str:
    from src.agent_tools.ocr_engine import extract_image_text
    result = extract_image_text(Path(path), min_confidence=_MIN_CONFIDENCE) or {}
    text = result.get("text")
    if not isinstance(text, str):
        text = "\n".join(str(line.get("t", "")) for line in result.get("lines", []))
    return text.strip()


# Seconds the latest OCR of each image took, so the chat can show it like the
# thinking time. Kept for the most recent images only.
_SECONDS: dict[str, float] = {}
_SECONDS_LOCK = threading.Lock()


def _remember_seconds(path: str, seconds: float) -> None:
    with _SECONDS_LOCK:
        if len(_SECONDS) >= 256:
            _SECONDS.pop(next(iter(_SECONDS)))
        _SECONDS[path] = round(seconds, 1)


def ocr_first_text(path: str) -> Optional[str]:
    """The image's text; "" when OCR found none; None when OCR is off, missing or slow."""
    if not _enabled():
        return None
    started = time.monotonic()
    try:
        text = _POOL.submit(_read, str(path)).result(timeout=_timeout())
        _remember_seconds(str(path), time.monotonic() - started)
    except _Timeout:
        logger.info("[ocr-first] OCR exceeded %.1fs; describing without it", _timeout())
        return None
    except Exception as exc:  # optional dependency missing, unreadable image, ...
        logger.info("[ocr-first] OCR unavailable (%s); describing without it", type(exc).__name__)
        return None
    return text if len(text) >= _MIN_CHARS else ""


def describe_prompt(ocr_text: Optional[str]) -> str:
    if ocr_text is None:
        return VISION_DESCRIBE_PROMPT
    if not ocr_text:
        return DESCRIBE_NO_TEXT_PROMPT
    return DESCRIBE_WITH_TEXT_PROMPT.format(ocr=ocr_text[:_MAX_PROMPT_CHARS])


# The prompt fences the OCR text in <<< >>>; a model sometimes copies that
# block back into its description, which would show the text twice.
_ECHOED_BLOCK_RE = re.compile(r"\n*[ \t]*<<<[ \t]*\n.*?\n[ \t]*>>>[ \t]*", re.S)


def with_text_block(description: str, ocr_text: Optional[str]) -> str:
    description = _ECHOED_BLOCK_RE.sub("", description or "").strip()
    if not ocr_text:
        return description
    block = f"Text in image:\n{ocr_text}"
    return f"{description}\n\n{block}" if description else block


def model_label(model: str, ocr_text: Optional[str]) -> str:
    """Credit OCR alongside the vision model when it supplied the text."""
    model = str(model or "").strip()
    if not ocr_text:
        return model
    return f"{model} + {OCR_MODEL_LABEL}" if model else OCR_MODEL_LABEL


TEXT_BLOCK_HEADER = "Text in image:"


def has_text_block(text: str) -> bool:
    """True when a description already carries the OCR text block."""
    text = text or ""
    return text.startswith(TEXT_BLOCK_HEADER + "\n") or f"\n\n{TEXT_BLOCK_HEADER}\n" in text


def cached_ocr_text(image_path: str, cache_path: str) -> str:
    """OCR text for a chat upload, read once and cached next to its vision text.

    An empty cache file records that OCR found no text; a missing one means
    OCR has not run (or was off, missing or slow) and is tried again.
    """
    try:
        with open(cache_path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        pass
    text = ocr_first_text(image_path)
    if text is None:
        return ""
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return text


def ocr_seconds_file(vision_dir: str, upload_id: str) -> str:
    """Where a chat upload's OCR time is kept, next to its cached vision text."""
    return os.path.join(vision_dir, f"{upload_id}.ocr.secs")


def save_ocr_seconds(image_path: str, seconds_file: str) -> None:
    """Record how long the latest OCR of image_path took, if it ran."""
    with _SECONDS_LOCK:
        seconds = _SECONDS.get(str(image_path))
    if seconds is None:
        return
    try:
        os.makedirs(os.path.dirname(seconds_file), exist_ok=True)
        with open(seconds_file, "w", encoding="utf-8") as f:
            f.write(f"{seconds:.1f}")
    except OSError:
        pass


def read_ocr_seconds(seconds_file: str) -> Optional[float]:
    try:
        with open(seconds_file, encoding="utf-8") as f:
            seconds = float(f.read().strip())
    except (OSError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def text_block_of(description: str) -> str:
    """The OCR text attached to a description, or ""."""
    description = description or ""
    if description.startswith(TEXT_BLOCK_HEADER + "\n"):
        return description[len(TEXT_BLOCK_HEADER) + 1:].strip()
    marker = f"\n\n{TEXT_BLOCK_HEADER}\n"
    return description.split(marker, 1)[1].strip() if marker in description else ""
