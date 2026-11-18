import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from src.agent_tools import ocr_engine
from src.agent_tools.media_tools import ExtractTextTool, InspectMediaTool
from src.agent_tools import TOOL_HANDLERS
from src.tool_execution import _active_workspace
from src.tool_schemas import FUNCTION_TOOL_SCHEMAS


def test_extract_text_schema_is_bounded_and_requires_a_path():
    schema = next(item["function"] for item in FUNCTION_TOOL_SCHEMAS if item["function"]["name"] == "extract_text")
    assert schema["parameters"]["additionalProperties"] is False
    assert schema["parameters"]["required"] == ["path"]
    assert schema["parameters"]["properties"]["max_results"]["maximum"] == 512
    assert TOOL_HANDLERS["extract_text"].__self__.__class__ is ExtractTextTool


def test_ocr_can_read_only_the_callers_uploaded_image_without_a_workspace(monkeypatch, tmp_path):
    from src import tool_utils
    source = tmp_path / 'owned.png'
    Image.new('RGB', (20, 20), 'white').save(source)
    def resolve(upload_id, *, owner, allow_admin):
        assert allow_admin is False
        return {'path': str(source)} if upload_id == 'fixture-upload.png' and owner == 'alice' else None
    monkeypatch.setattr(tool_utils, 'get_upload_handler', lambda: SimpleNamespace(resolve_upload=resolve))
    monkeypatch.setattr(ocr_engine, 'extract_image_text', lambda path, **kwargs: {'lines': [{'t': '42'}]})
    token = _active_workspace.set(None)
    try:
        args = json.dumps({'path': 'odysseus://attachment/fixture-upload.png'})
        owned = asyncio.run(ExtractTextTool().execute(args, {'owner': 'alice'}))
        other = asyncio.run(ExtractTextTool().execute(args, {'owner': 'bob'}))
        anonymous = asyncio.run(ExtractTextTool().execute(args, {}))
        host = asyncio.run(ExtractTextTool().execute(json.dumps({'path': str(source)}), {'owner': 'alice'}))
        traversal = asyncio.run(ExtractTextTool().execute(json.dumps({'path': 'odysseus://attachment/../fixture-upload.png'}), {'owner': 'alice'}))
    finally:
        _active_workspace.reset(token)
    assert owned['exit_code'] == 0 and owned['ocr']['lines'][0]['t'] == '42'
    assert other['exit_code'] == anonymous['exit_code'] == host['exit_code'] == traversal['exit_code'] == 1


def test_ocr_engine_returns_compact_centers_and_can_filter_numbers(monkeypatch, tmp_path: Path):
    output = SimpleNamespace(
        boxes=[[[0, 0], [10, 0], [10, 10], [0, 10]], [[20, 20], [30, 20], [30, 30], [20, 30]]],
        txts=["Label", "42"], scores=[0.99, 0.98],
    )
    monkeypatch.setattr(ocr_engine, "_engine", lambda: lambda _path: output)
    result = ocr_engine.extract_image_text(tmp_path / "unused.png", numeric_only=True)
    assert result["lines"] == [{"t": "42", "p": 0.98, "xy": [25.0, 25.0]}]


def test_extract_text_is_workspace_confined(monkeypatch, tmp_path: Path):
    Image.new("RGB", (20, 20), "white").save(tmp_path / "source.png")
    monkeypatch.setattr(ocr_engine, "extract_image_text", lambda _path, **_kwargs: {
        "legend": {"t": "text", "p": "confidence", "xy": "pixel center"}, "count": 1,
        "returned": 1, "truncated": False, "lines": [{"t": "FRESH", "p": 1.0, "xy": [10.0, 10.0]}],
    })
    token = _active_workspace.set(str(tmp_path))
    try:
        success = asyncio.run(ExtractTextTool().execute(json.dumps({"path": "/workspace/source.png"}), {}))
        escaped = asyncio.run(ExtractTextTool().execute(json.dumps({"path": "/etc/passwd"}), {}))
    finally:
        _active_workspace.reset(token)
    assert success["ocr"]["lines"][0]["t"] == "FRESH"
    assert escaped["exit_code"] == 1 and "workspace" in escaped["error"]


def test_extract_text_accepts_workspace_uri_alias_without_weakening_confinement(monkeypatch, tmp_path: Path):
    Image.new("RGB", (20, 20), "white").save(tmp_path / "source.png")
    monkeypatch.setattr(ocr_engine, "extract_image_text", lambda _path, **_kwargs: {
        "lines": [{"t": "VISIBLE", "p": 1.0, "xy": [10.0, 10.0]}],
    })
    token = _active_workspace.set(str(tmp_path))
    try:
        result = asyncio.run(ExtractTextTool().execute(json.dumps({
            "path": "odysseus://workspace/source.png",
        }), {}))
        escaped = asyncio.run(ExtractTextTool().execute(json.dumps({
            "path": "odysseus://workspace/../outside.png",
        }), {}))
    finally:
        _active_workspace.reset(token)

    assert result["exit_code"] == 0
    assert result["ocr"]["lines"][0]["t"] == "VISIBLE"
    assert escaped["exit_code"] == 1


def test_extract_text_renders_and_ocr_scans_pdf_pages(monkeypatch, tmp_path: Path):
    source = tmp_path / "scan.pdf"
    pages = [Image.new("RGB", (40, 40), "white") for _ in range(2)]
    pages[0].save(source, "PDF", save_all=True, append_images=pages[1:])
    calls = []

    def fake_ocr(path, **_kwargs):
        calls.append(Path(path).name)
        return {
            "count": 1,
            "returned": 1,
            "truncated": False,
            "lines": [{"t": "VISIBLE", "p": 1.0, "xy": [10.0, 10.0]}],
        }

    monkeypatch.setattr(ocr_engine, "extract_image_text", fake_ocr)
    token = _active_workspace.set(str(tmp_path))
    try:
        result = asyncio.run(ExtractTextTool().execute(
            json.dumps({"path": "/workspace/scan.pdf"}),
            {},
        ))
    finally:
        _active_workspace.reset(token)

    assert result["exit_code"] == 0
    assert result["ocr"]["page_count"] == 2
    assert result["ocr"]["pages_processed"] == 2
    assert [line["page"] for line in result["ocr"]["lines"]] == [1, 2]
    assert len(calls) == 2


def test_inspect_media_auto_augments_exact_text_queries_only(monkeypatch, tmp_path: Path):
    Image.new("RGB", (20, 20), "white").save(tmp_path / "source.png")
    monkeypatch.setattr(ocr_engine, "extract_image_text", lambda _path, **_kwargs: {
        "legend": {"t": "text", "p": "confidence", "xy": "pixel center"}, "count": 1,
        "returned": 1, "truncated": False, "lines": [{"t": "42", "p": .99, "xy": [10.0, 10.0]}],
    })
    token = _active_workspace.set(str(tmp_path))
    try:
        exact = asyncio.run(InspectMediaTool().execute(json.dumps({"path": "/workspace/source.png", "query": "numbered labels"}), {}))
        general = asyncio.run(InspectMediaTool().execute(json.dumps({"path": "/workspace/source.png", "query": "overall composition"}), {}))
    finally:
        _active_workspace.reset(token)
    assert exact["ocr_augmented"] is True and '"t":"42"' in exact["output"]
    assert "ocr_augmented" not in general


def _box(text, x0, x1, y):
    return {"t": text, "p": 0.99, "min_x": x0, "max_x": x1, "min_y": y - 6, "max_y": y + 6,
            "cx": (x0 + x1) / 2, "cy": y, "h": 12}


def test_two_column_page_reads_each_column_top_to_bottom():
    from src.agent_tools.ocr_engine import _reading_text
    header = [_box("Chapter 3 - Field Notes", 60, 540, 10)]
    left = [_box(f"left line {i}", 40, 280, 40 + 20 * i) for i in range(6)]
    right = [_box(f"right line {i}", 320, 560, 40 + 20 * i) for i in range(6)]
    text = _reading_text(header + left + right).splitlines()
    assert text == (["Chapter 3 - Field Notes"] + [f"left line {i}" for i in range(6)]
                    + [f"right line {i}" for i in range(6)])


def test_receipt_prices_stay_on_their_item_row():
    from src.agent_tools.ocr_engine import _reading_text
    rows = []
    for i in range(12):
        rows += [_box(f"Item number {i}", 30, 200, 20 + 20 * i), _box(f"{i}.25", 420, 470, 21 + 20 * i)]
    assert _reading_text(rows).splitlines() == [f"Item number {i} {i}.25" for i in range(12)]


def _slanted_box(x, y, w, h, degrees):
    import math
    a = math.radians(degrees)
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    return [[x + cx * math.cos(a) - cy * math.sin(a), y + cx * math.sin(a) + cy * math.cos(a)] for cx, cy in corners]


def test_slanted_photo_keeps_its_lines(monkeypatch, tmp_path: Path):
    # Three lines of two words, photographed at 40 degrees: each line's words
    # sit along the slant, and the lines step down the page at a right angle.
    import math
    a = math.radians(40)
    words = [("USES:", "Great"), ("Purple", "glue"), ("Dries", "clear")]
    boxes, txts = [], []
    for row, (first, second) in enumerate(words):
        base_x, base_y = 300 - row * 40 * math.sin(a), 100 + row * 40 * math.cos(a)
        for col, word in enumerate((first, second)):
            boxes.append(_slanted_box(base_x + col * 130 * math.cos(a), base_y + col * 130 * math.sin(a), 110, 24, 40))
            txts.append(word)
    output = SimpleNamespace(boxes=boxes, txts=txts, scores=[0.99] * len(txts))
    monkeypatch.setattr(ocr_engine, "_engine", lambda: lambda _path: output)
    result = ocr_engine.extract_image_text(tmp_path / "unused.png")
    assert result["text"].splitlines() == ["USES: Great", "Purple glue", "Dries clear"]


def test_level_text_is_not_rotated():
    level = [[[0, 0], [100, 0], [100, 20], [0, 20]], [[0, 40], [80, 41], [80, 61], [0, 60]]]
    assert abs(ocr_engine._text_tilt(level)) < 3


def test_text_in_two_directions_is_read_as_two_blocks(monkeypatch, tmp_path: Path):
    # A level sign with a label running up its right edge (90 degrees off).
    boxes = [
        [[0, 0], [200, 0], [200, 30], [0, 30]],          # OPEN 24 HOURS
        [[0, 50], [150, 50], [150, 80], [0, 80]],        # Coffee $1.50
        [[0, 100], [150, 100], [150, 130], [0, 130]],    # Pie $4.25
        [[400, 300], [400, 100], [430, 100], [430, 300]],  # MADE IN USA, read bottom to top
        [[450, 300], [450, 120], [480, 120], [480, 300]],  # LOT 1234
    ]
    output = SimpleNamespace(boxes=boxes, txts=["OPEN 24 HOURS", "Coffee $1.50", "Pie $4.25", "MADE IN USA", "LOT 1234"],
                             scores=[0.99] * 5)
    monkeypatch.setattr(ocr_engine, "_engine", lambda: lambda _path: output)
    lines = ocr_engine.extract_image_text(tmp_path / "unused.png")["text"].splitlines()
    assert lines[:3] == ["OPEN 24 HOURS", "Coffee $1.50", "Pie $4.25"]
    assert sorted(lines[3:]) == ["LOT 1234", "MADE IN USA"]        # its own block, one line each


def test_single_letters_join_the_text_next_to_them(monkeypatch, tmp_path: Path):
    # A big slanted block and a small level one; a lone "F9" key sits by the
    # level block and must be read with it, not with the bigger block.
    boxes = [_slanted_box(100, 100 + 40 * row, 160, 24, 45) for row in range(4)]
    boxes += [[[600, 500], [660, 500], [660, 520], [600, 520]],      # F10
              [[670, 500], [730, 500], [730, 520], [670, 520]],      # F11
              [[580, 500], [596, 500], [596, 520], [580, 520]]]      # F9: too squat to have a direction
    txts = ["one two", "three four", "five six", "seven eight", "F10", "F11", "F9"]
    output = SimpleNamespace(boxes=boxes, txts=txts, scores=[0.99] * len(txts))
    monkeypatch.setattr(ocr_engine, "_engine", lambda: lambda _path: output)
    lines = ocr_engine.extract_image_text(tmp_path / "unused.png")["text"].splitlines()
    assert lines[-1] == "F9 F10 F11"
