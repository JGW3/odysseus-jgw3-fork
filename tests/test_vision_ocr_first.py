"""OCR on every image; the vision model gets a short describe-only prompt."""

import time
from pathlib import Path

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


def test_prompt_says_ocr_can_be_wrong(monkeypatch):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "Vout=1.3V+0.102V")
    prompt = vision_ocr.describe_prompt(vision_ocr.ocr_first_text("exam.jpg"))
    assert "it can be wrong, so trust the image" in prompt
    # Asking it to also describe handwriting made gemma4 think through its
    # whole token budget on a handwritten exam page (2 of 3 runs empty).
    assert "handwriting" not in prompt


def test_ocr_first_drops_low_confidence_fragments(monkeypatch):
    from src.agent_tools import ocr_engine
    seen = {}

    def fake_extract(path, **kwargs):
        seen.update(kwargs)
        return {"text": "kept"}

    monkeypatch.setattr(ocr_engine, "extract_image_text", fake_extract)
    assert vision_ocr._read("page.jpg") == "kept"
    assert seen["min_confidence"] == vision_ocr._MIN_CONFIDENCE > 0.5


@pytest.mark.parametrize("echo", [
    "\n\n<<<\nNAME: Jane Doe\nPage 1 of 5\n>>>",
    "\n<<<\nNAME: Jane Doe\nPage 1 of 5\n>>>\n",
])
def test_an_echoed_ocr_block_is_not_kept_twice(echo):
    described = "The first page of an exam.\n\nA red circle holds the score." + echo
    caption = vision_ocr.with_text_block(described, "NAME: Jane Doe\nPage 1 of 5")
    assert caption == ("The first page of an exam.\n\nA red circle holds the score.\n\n"
                       "Text in image:\nNAME: Jane Doe\nPage 1 of 5")
    assert "<<<" not in caption and ">>>" not in caption


def test_prompt_and_echo_markers_stay_in_step():
    prompt = vision_ocr.describe_prompt("SIGN")
    assert "<<<\nSIGN\n>>>" in prompt
    assert vision_ocr.with_text_block("Desc.\n\n<<<\nSIGN\n>>>", "SIGN") == "Desc.\n\nText in image:\nSIGN"


def test_text_block_detection():
    assert vision_ocr.has_text_block("A sign.\n\nText in image:\nSTOP")
    assert vision_ocr.has_text_block("Text in image:\nSTOP")
    assert not vision_ocr.has_text_block("A sign that says Text in image: no")


def test_chat_ocr_is_read_once_and_cached(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(vision_ocr, "_read", lambda path: calls.append(path) or "Rain Check")
    cache = str(tmp_path / ".vision" / "img.ocr.txt")
    assert vision_ocr.cached_ocr_text("img.png", cache) == "Rain Check"
    assert vision_ocr.cached_ocr_text("img.png", cache) == "Rain Check"
    assert len(calls) == 1


def test_no_text_is_cached_but_missing_ocr_is_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "")
    empty = str(tmp_path / "a.ocr.txt")
    assert vision_ocr.cached_ocr_text("a.png", empty) == "" and Path(empty).exists()
    monkeypatch.setattr(vision_ocr, "_read", lambda path: (_ for _ in ()).throw(RuntimeError("no engine")))
    missing = str(tmp_path / "b.ocr.txt")
    assert vision_ocr.cached_ocr_text("b.png", missing) == "" and not Path(missing).exists()


def test_background_caption_is_ocr_first(monkeypatch, tmp_path):
    import asyncio
    from src import document_processor as dp
    from src import llm_core
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    monkeypatch.setattr(vision_ocr, "_read", lambda path: "Rain Check  a later offer")
    sent = {}

    async def fake_call(url, model, messages, **kwargs):
        sent["prompt"] = messages[0]["content"][0]["text"]
        return "A page from a glossary."
    monkeypatch.setattr(llm_core, "llm_call_async", fake_call)
    text = asyncio.run(dp.describe_image_for_caption(str(image), "http://m.invalid/v1", "gemma4:q5c"))
    assert "Don't copy out longer text" in sent["prompt"] and "Rain Check" in sent["prompt"]
    assert text == "A page from a glossary.\n\nText in image:\nRain Check  a later offer"


def test_only_one_background_caption_function():
    source = (Path(__file__).resolve().parents[1] / "src/document_processor.py").read_text(encoding="utf-8")
    assert source.count("async def describe_image_for_caption(") == 1


def test_text_block_is_recovered_from_a_description():
    assert vision_ocr.text_block_of("A page.\n\nText in image:\nRain Check\nRainbow") == "Rain Check\nRainbow"
    assert vision_ocr.text_block_of("Text in image:\nSTOP") == "STOP"
    assert vision_ocr.text_block_of("A cat on a couch.") == ""





def test_chat_shows_the_ocr_text_under_the_image():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    assert "export function attachOcrBlock(att, { plain = false } = {}) {" in renderer
    assert "OCR: RapidOCR · ${lines} line" in renderer                  # history turn without a reply
    chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
    assert chat.count("attachOcrBlock(_att, { plain: true })") == 2      # live turns: label only
    handler = (root / "src/chat_handler.py").read_text(encoding="utf-8")
    assert handler.count('_m["ocr"] = ') == 3


def test_gallery_shows_image_text_in_its_own_panel():
    js = (Path(__file__).resolve().parents[1] / "static/js/gallery.js").read_text(encoding="utf-8")
    assert "function _splitTextBlock(caption)" in js
    assert '<label>OCR text in image</label>`' in js
    assert '<pre class="attach-ocr-text gallery-ocr-text">${esc(imageText)}</pre>' in js


def test_user_bubble_hides_the_ocr_text_block():
    renderer = (Path(__file__).resolve().parents[1] / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    assert "\\[Text read from this image by OCR" in renderer


def _run_caption_sections(caption, source):
    import json as _json
    import subprocess
    js = (Path(__file__).resolve().parents[1] / "static/js/gallery.js").read_text(encoding="utf-8")
    parts = []
    for name in ("function _captionSources(source) {", "function _sourceLabel(text, esc) {",
                 "function _splitTextBlock(caption) {", "function _captionSections(caption, source, esc) {"):
        start = js.index(name)
        parts.append(js[start:js.index("\n}\n", start) + 2])
    esc = "const esc = (t) => String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;');"
    script = esc + "\n".join(parts) + f"\nconsole.log(_captionSections({_json.dumps(caption)}, {_json.dumps(source)}, esc));"
    return subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout


def test_gallery_description_then_ocr_text_behind_one_toggle():
    html = _run_caption_sections(
        "A Notepad window.\n\nIt shows program output.\n\nText in image:\nC-List using generics\nList Length: 5",
        "vision:gemma4:q5c + RapidOCR")
    order = [html.index(s) for s in ("<label>AI description</label>", "show more", "Vision: gemma4:q5c",
                                     "<label>OCR text in image</label>", "C-List using generics",
                                     "OCR: RapidOCR", "show less")]
    assert order == sorted(order)
    assert 'id="gallery-caption-ocr" hidden' in html          # collapsed until "show more"
    assert html.count("show less") == 1 and html.count("show more") == 1


def test_short_caption_without_text_has_no_toggle():
    html = _run_caption_sections("A mountain at dusk.", "vision:gemma4:q5c")
    assert "show more" not in html and "Vision: gemma4:q5c" in html and "OCR text" not in html


def test_ocr_only_caption_shows_the_text_openly():
    html = _run_caption_sections("Text in image:\nTOTAL 26.27", "vision:RapidOCR")
    assert "AI description" not in html and 'id="gallery-caption-ocr">' in html and "OCR: RapidOCR" in html


def test_reply_gets_the_text_from_the_users_images():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    assert "export function imageTextSection(items)" in renderer
    assert "if (role === 'user') setPendingImageText(attachments, wrap);" in renderer
    assert renderer.count("appendPendingImageText(") >= 3          # standard bubble, agent bubbles, definition
    assert "e.target.closest('.attach-ocr')) return;" in renderer   # the OCR label doesn't open the lightbox
    chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
    assert "setPendingImageText(json.data, _ub);" in chat and "if (holder) appendPendingImageText(holder);" in chat


def test_photo_ocr_expander_becomes_a_label_once_the_reply_shows_the_text():
    renderer = (Path(__file__).resolve().parents[1] / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    start = renderer.index("export function appendPendingImageText(msgEl) {")
    body = renderer[start:renderer.index("\n}\n", start)]
    # Only after the reply really has the section, and only for that turn's user message.
    assert "if (target.querySelector('.image-text-section')) _flattenAttachOcr(_pendingImageTextOwner);" in body
    assert "_pendingImageTextOwner = null;" in body
    flatten = renderer[renderer.index("function _flattenAttachOcr(userMsgEl) {"):start]
    assert "querySelectorAll('details.attach-ocr')" in flatten
    assert "label.className = 'attach-vision-model attach-ocr';" in flatten   # duplicate and lightbox guards still match
    assert "label.textContent = 'OCR: RapidOCR';" in flatten                  # the line count is in the reply's bar


def test_ocr_time_is_recorded_and_read_back(monkeypatch, tmp_path):
    monkeypatch.setattr(vision_ocr, "_read", lambda path: time.sleep(0.2) or "OPEN 24 HOURS")
    image = str(tmp_path / "sign.png")
    assert vision_ocr.ocr_first_text(image) == "OPEN 24 HOURS"
    seconds_file = vision_ocr.ocr_seconds_file(str(tmp_path / ".vision"), "abc123")
    vision_ocr.save_ocr_seconds(image, seconds_file)
    seconds = vision_ocr.read_ocr_seconds(seconds_file)
    assert seconds is not None and 0.1 <= seconds < 1.5
    # No OCR run for this image, nothing recorded: no time rather than a wrong one.
    other = vision_ocr.ocr_seconds_file(str(tmp_path / ".vision"), "never-ran")
    vision_ocr.save_ocr_seconds(str(tmp_path / "other.png"), other)
    assert vision_ocr.read_ocr_seconds(other) is None


def test_chat_attachments_carry_the_ocr_time():
    handler = (Path(__file__).resolve().parents[1] / "src/chat_handler.py").read_text(encoding="utf-8")
    assert handler.count("_set_ocr_seconds(_m, att_id)") == 3          # cached caption, OCR-only, vision paths
    assert handler.count("save_ocr_seconds(file_info[\"path\"],") == 2


def test_image_text_section_matches_the_thinking_block_under_it():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    section = renderer[renderer.index("export function imageTextSection(items) {"):]
    assert "box.className = 'thinking-section image-text-section';" in section
    assert "header.dataset.thinkingId = id;" in section               # the thinking block's own toggle handles it
    assert "toggle.id = id + '-toggle';" in section and "content.id = id;" in section
    assert ".toFixed(1) + 's'" in section
    # "1.3s · 4 lines" in the bar: time first, like the thinking block's time then tokens.
    assert section.index(".toFixed(1) + 's');") < section.index("facts.push(`${lines} line")
    append = renderer[renderer.index("export function appendPendingImageText(msgEl) {"):]
    assert "if (thinking) thinking.after(section);" in append and "else target.prepend(section);" in append
    css = (root / "static/css/09-gallery.css").read_text(encoding="utf-8")
    assert "--ocr-accent: var(--hl-function, #61afef);" in css
    chat_css = (root / "static/css/03-agent-chat.css").read_text(encoding="utf-8")
    # "Hide thinking" in Settings must not hide the OCR text too.
    assert "body.hide-thinking .thinking-section:not(.image-text-section) { display: none !important; }" in chat_css


def test_live_turn_shows_a_plain_ocr_label_and_the_bar_drops_rapidocr():
    root = Path(__file__).resolve().parents[1]
    chat = (root / "static/js/chat.js").read_text(encoding="utf-8")
    # The attachment event of a live turn: the reply is about to show the text,
    # so the photo gets the plain label, never the expander.
    assert chat.count("attachOcrBlock(_att, { plain: true })") == 2
    assert "attachOcrBlock(_att)" not in chat
    renderer = (root / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    assert "export function attachOcrBlock(att, { plain = false } = {}) {" in renderer
    assert "const label = 'text from image' + (items.length > 1 ? 's' : '');" in renderer


def test_ocr_text_uses_the_thinking_blocks_text_style():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "static/js/chatRenderer.js").read_text(encoding="utf-8")
    section = renderer[renderer.index("export function imageTextSection(items) {"):]
    assert "const body = document.createElement('div');" in section     # no <pre> code-block styling
    css = (root / "static/css/09-gallery.css").read_text(encoding="utf-8")
    rule = css[css.index(".thinking-content-inner .image-text-body {"):]
    rule = rule[:rule.index("}")]
    assert "font-size" not in rule and "white-space: pre-wrap" in rule
