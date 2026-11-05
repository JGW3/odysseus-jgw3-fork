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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
from pathlib import Path
from typing import Optional

from src.constants import VISION_DESCRIBE_PROMPT

logger = logging.getLogger(__name__)

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-first")
_MIN_CHARS = 3
_MAX_PROMPT_CHARS = 4000
OCR_MODEL_LABEL = "RapidOCR"

DESCRIBE_WITH_TEXT_PROMPT = (
    "Describe this image: a one or two sentence overview, a blank line, then "
    "the details. Say what any text is and where; if it is short, like a sign "
    "or a label, say what it says. Don't copy out longer text such as a recipe "
    "or a page; just say what it is. The full text, read separately, will be "
    "attached below your description:\n<<<\n{ocr}\n>>>"
)
DESCRIBE_NO_TEXT_PROMPT = (
    "Describe this image: a one or two sentence overview, a blank line, then "
    "the details."
)


def _enabled() -> bool:
    return os.getenv("ODYSSEUS_OCR_FIRST", "1").strip().lower() not in {"0", "false", "no", "off"}


def _timeout() -> float:
    try:
        return max(0.5, float(os.getenv("ODYSSEUS_OCR_FIRST_TIMEOUT", "8")))
    except ValueError:
        return 8.0


def _read(path: str) -> str:
    from src.agent_tools.ocr_engine import extract_image_text
    result = extract_image_text(Path(path)) or {}
    text = result.get("text")
    if not isinstance(text, str):
        text = "\n".join(str(line.get("t", "")) for line in result.get("lines", []))
    return text.strip()


def ocr_first_text(path: str) -> Optional[str]:
    """The image's text; "" when OCR found none; None when OCR is off, missing or slow."""
    if not _enabled():
        return None
    try:
        text = _POOL.submit(_read, str(path)).result(timeout=_timeout())
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


def with_text_block(description: str, ocr_text: Optional[str]) -> str:
    description = (description or "").strip()
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
