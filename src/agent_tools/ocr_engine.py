"""Bounded local OCR primitives shared by Odysseus media tools."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
import tempfile

_OCR_QUERY_RE = re.compile(r"(?:\b(?:ocr|text|words?|labels?|numbers?|numbered|subtitle|receipt)\b|文字|文本|字幕|编号|数字|标签|票据)", re.I)
_NUMERIC_QUERY_RE = re.compile(r"(?:\b(?:numbers?|numbered|digits?)\b|编号|数字)", re.I)
_CJK_RE = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
_NO_LEAD_SPACE = set(",.;:!?%)]}\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f")
_NO_TRAIL_SPACE = set("([{$\u3008\u300a\u300c\u300e\uff08")
_MAX_SIDE_DEFAULT = 2400

def query_requests_ocr(query: object) -> bool:
    return bool(_OCR_QUERY_RE.search(str(query or "")))

def query_requests_numbers(query: object) -> bool:
    return bool(_NUMERIC_QUERY_RE.search(str(query or "")))

@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise RuntimeError("local OCR requires the optional rapidocr and onnxruntime packages") from exc
    return RapidOCR()

def _prepare_image(path: Path) -> tuple[str, str | None]:
    """Downscale huge camera images; return (path_to_read, temp_path_or_None)."""
    try:
        max_side = int(os.getenv("ODYSSEUS_OCR_MAX_SIDE", str(_MAX_SIDE_DEFAULT)))
    except ValueError:
        max_side = _MAX_SIDE_DEFAULT
    if max_side <= 0:
        return str(path), None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return str(path), None
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            if max(width, height) <= max_side:
                return str(path), None
            scale = max_side / float(max(width, height))
            resized = img.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)
            if resized.mode not in ("RGB", "L"):
                resized = resized.convert("RGB")
            handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            handle.close()
            resized.save(handle.name, "PNG")
            resized.close()
            return handle.name, handle.name
    except Exception:
        return str(path), None

def _box_metrics(box):
    points = [(float(x), float(y)) for x, y in box]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys), sum(xs) / len(xs), sum(ys) / len(ys), max(1.0, max(ys) - min(ys))

def _same_line(a, b) -> bool:
    overlap = min(a["max_y"], b["max_y"]) - max(a["min_y"], b["min_y"])
    return overlap >= 0.4 * min(a["h"], b["h"]) or abs(a["cy"] - b["cy"]) <= 0.5 * min(a["h"], b["h"])

def _needs_space(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if prev[-1] in _NO_TRAIL_SPACE or nxt[0] in _NO_LEAD_SPACE:
        return False
    if _CJK_RE.match(prev[-1]) or _CJK_RE.match(nxt[0]):
        return False
    return True

def _join_line(parts: list[str]) -> str:
    out = ""
    for raw in parts:
        text = re.sub(r"[ \t]+", " ", str(raw or "")).strip()
        if not text:
            continue
        out = text if not out else (out + (" " if _needs_space(out, text) else "") + text)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\s+([,.;:!?%)\]])", r"\1", out)
    return out.strip()

def _column_split(entries: list[dict]) -> float | None:
    """x of the empty gutter between two text columns, or None for one column.

    The gutter is the widest x-band in the middle of the page that (almost)
    no text box crosses, with real text on both sides.
    """
    if len(entries) < 8:
        return None
    left = min(e["min_x"] for e in entries)
    right = max(e["max_x"] for e in entries)
    width = right - left
    if width <= 0:
        return None
    bins = 200
    cover = [0] * bins
    for e in entries:
        a = int((e["min_x"] - left) / width * (bins - 1))
        b = int((e["max_x"] - left) / width * (bins - 1))
        for i in range(max(a, 0), min(b, bins - 1) + 1):
            cover[i] += 1
    allowed = max(1, len(entries) // 40)       # a few boxes may straddle it
    best = None
    i = int(bins * 0.2)
    while i < int(bins * 0.8):
        if cover[i] <= allowed:
            j = i
            while j < bins and cover[j] <= allowed:
                j += 1
            if j - i >= 2 and (best is None or j - i > best[1] - best[0]):
                best = (i, j)
            i = j
        else:
            i += 1
    if best is None:
        return None
    split = left + (best[0] + best[1]) / 2 / (bins - 1) * width
    left_side = [e["max_x"] - e["min_x"] for e in entries if e["max_x"] <= split]
    right_side = [e["max_x"] - e["min_x"] for e in entries if e["min_x"] >= split]
    if min(len(left_side), len(right_side)) < max(3, len(entries) // 6):
        return None
    # Text columns are wide on both sides; a receipt's prices or a table's
    # numbers form a narrow strip that must stay on its row.
    median = lambda widths: sorted(widths)[len(widths) // 2]
    if min(median(left_side), median(right_side)) < 0.25 * width:
        return None
    return split


def _reading_text(entries: list[dict]) -> str:
    """Reading-order text: columns left to right, each top to bottom.

    Boxes that cross the gutter (a page header, a full-width line) divide the
    page into bands, so text above and below them keeps its place.
    """
    split = _column_split(entries)
    if split is None:
        return _rows_text(entries)
    spanning = sorted((e for e in entries if e["min_x"] < split < e["max_x"]), key=lambda e: e["cy"])
    columns = [e for e in entries if not (e["min_x"] < split < e["max_x"])]
    out, top = [], float("-inf")
    for divider in spanning + [None]:
        bottom = divider["cy"] if divider else float("inf")
        band = [e for e in columns if top <= e["cy"] < bottom]
        for side in ([e for e in band if e["cx"] < split], [e for e in band if e["cx"] >= split]):
            text = _rows_text(side)
            if text:
                out.append(text)
        if divider:
            out.append(_rows_text([divider]))
            top = bottom
    return "\n".join(part for part in out if part)


def _rows_text(entries: list[dict]) -> str:
    rows: list[dict] = []
    for entry in sorted(entries, key=lambda item: (item["cy"], item["min_x"])):
        for row in rows:
            if _same_line(entry, row):
                row["items"].append(entry)
                row["cy"] = sum(item["cy"] for item in row["items"]) / len(row["items"])
                row["h"] = max(row["h"], entry["h"])
                row["max_y"] = max(row["max_y"], entry["max_y"])
                row["min_y"] = min(row["min_y"], entry["min_y"])
                break
        else:
            rows.append({"cy": entry["cy"], "h": entry["h"], "min_y": entry["min_y"], "max_y": entry["max_y"], "items": [entry]})
    rows.sort(key=lambda row: row["cy"])
    lines = []
    for row in rows:
        row["items"].sort(key=lambda item: item["min_x"])
        text = _join_line([item["t"] for item in row["items"]])
        if text:
            lines.append(text)
    return "\n".join(lines)

def extract_image_text(path: Path, *, include_layout: bool = False, numeric_only: bool = False,
                       min_confidence: float = 0.5, max_results: int = 512) -> dict:
    read_path, temp_path = _prepare_image(path)
    try:
        result = _engine()(read_path)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    lines, entries, accepted = [], [], 0
    boxes = [] if result.boxes is None else result.boxes
    texts = [] if result.txts is None else result.txts
    scores = [] if result.scores is None else result.scores
    for box, raw_text, raw_score in zip(boxes, texts, scores):
        text, score = str(raw_text).strip(), float(raw_score)
        if not text or score < min_confidence or (numeric_only and not any(c.isdigit() for c in text)):
            continue
        accepted += 1
        if len(lines) >= max_results:
            continue
        points = [[round(float(x), 1), round(float(y), 1)] for x, y in box]
        metrics = _box_metrics(box)
        line = {"t": text, "p": round(score, 3), "xy": [round(metrics[4], 1), round(metrics[5], 1)]}
        if include_layout:
            line["box"] = points
        lines.append(line)
        entries.append({"t": text, "p": score, "min_x": metrics[0], "max_x": metrics[1],
                        "min_y": metrics[2], "max_y": metrics[3], "cx": metrics[4], "cy": metrics[5], "h": metrics[6]})
    text = _reading_text(entries)
    return {"legend": {"t": "text", "p": "confidence", "xy": "pixel center"}, "count": accepted,
            "returned": len(lines), "truncated": accepted > len(lines), "lines": lines, "text": text}
