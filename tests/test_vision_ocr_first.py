"""OCR on every image; the vision model gets a short describe-only prompt."""

import time

import pytest

from src import vision_ocr
from src.constants import VISION_DESCRIBE_PROMPT


def test_text_found_uses_the_short_prompt_and_appends_the_text(monkeypatch):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "OPEN 24 HOURS\nGreen chili stew $6.50")
    text = vision_ocr.ocr_first_text("sign.png")
    prompt = vision_ocr.describe_prompt(text)
    assert "if it is short, like a sign" in prompt and "Don't copy out longer text" in prompt
    assert "Green chili stew $6.50" in prompt
    assert len(prompt) < len(VISION_DESCRIBE_PROMPT) + len(text) + 200
    caption = vision_ocr.with_text_block("A diner at night.\n\nA neon sign above the door.", text)
    assert caption == ("A diner at night.\n\nA neon sign above the door.\n\n"
                       "Text in image:\nOPEN 24 HOURS\nGreen chili stew $6.50")


@pytest.mark.parametrize("found", ["", "a"])                 # nothing, or a stray speck read as a letter
def test_no_text_found_asks_only_for_a_description(monkeypatch, found):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: found)
    text = vision_ocr.ocr_first_text("photo.png")
    assert text == ""
    assert vision_ocr.describe_prompt(text) == vision_ocr.DESCRIBE_NO_TEXT_PROMPT
    assert "transcribe" not in vision_ocr.DESCRIBE_NO_TEXT_PROMPT.lower()
    assert vision_ocr.with_text_block("A mountain at dusk.", text) == "A mountain at dusk."


def test_missing_ocr_engine_keeps_the_full_describe_prompt(monkeypatch):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: (_ for _ in ()).throw(RuntimeError("rapidocr not installed")))
    text = vision_ocr.ocr_first_text("photo.png")
    assert text is None
    assert vision_ocr.describe_prompt(text) == VISION_DESCRIBE_PROMPT


def test_text_alone_when_there_is_no_description():
    assert vision_ocr.with_text_block("", "TOTAL 26.27") == "Text in image:\nTOTAL 26.27"


def test_slow_ocr_is_abandoned(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_OCR_FIRST_TIMEOUT", "0.5")
    monkeypatch.setattr(vision_ocr, "_read", lambda path: time.sleep(2) or "late text")
    started = time.monotonic()
    assert vision_ocr.ocr_first_text("huge.png") is None
    assert time.monotonic() - started < 1.5


def test_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_OCR_FIRST", "0")
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "should not run")
    assert vision_ocr.ocr_first_text("sign.png") is None


def test_vision_disabled_still_returns_the_ocr_text(monkeypatch):
    from src import document_processor as dp
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "TOTAL 26.27")
    monkeypatch.setattr(dp, "_load_vl_settings", lambda: {"vision_enabled": False})
    result = dp.analyze_image_with_vl_result("receipt.png")
    assert result == {"text": "Text in image:\nTOTAL 26.27", "model": "RapidOCR"}


def test_model_label_credits_ocr_when_it_supplied_the_text():
    assert vision_ocr.model_label("gemma4:q5c", "OPEN 24 HOURS") == "gemma4:q5c + RapidOCR"
    assert vision_ocr.model_label("gemma4:q5c", "") == "gemma4:q5c"
    assert vision_ocr.model_label("gemma4:q5c", None) == "gemma4:q5c"
