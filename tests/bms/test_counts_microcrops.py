"""Tests for TASK-014:
1. PDF text layer first with bounding boxes (extended with multi-line/stacked tag support).
2. Detection of sheets with and without a text layer.
3. Classification of confident vs ambiguous tags.
4. Micro-crop extraction around ambiguous tags.
5. Vision question using micro-crops only (keeping one request per sheet).
6. Fallback to full sheet tiles for sheets with no text layer.
7. Counting symbols without tags when schedule expects untagged units.
8. Verification of image token savings per sheet on an invented PDF.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

TESTS = Path(__file__).resolve().parents[1]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from pdfs import FILLER, Page, make_pdf

from bms import counts
from bms.counts import Box, CountResult
from bms.counts_text import (
    canonical,
    classify_located_boxes,
    has_text_layer,
    image_tokens,
    located_boxes,
    token_savings,
)
from bms.counts_vision import (
    cut_micro_crops,
    cut_tiles,
    tile_grid,
)
from bms.model import Count, Family, Job, OtherCount, Ref, System
from estimator.catalogue.documents import Document
from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet

W, H = 1728, 1152          # 24 x 16 inch sheet in points (2880 x 1920 pixels at 120 dpi)


def _catalogue(pdf: Path, pages: list[tuple[int, str, str, str]], discipline: str = "Mechanical"):
    document = Document(pdf, pdf.name, "drawings", "base", len(pages))
    job = SimpleNamespace(name="26-9999", root=pdf.parent, documents=(document,))
    records = tuple(PageRecord(pdf.name, n, "text", text, 0, True) for n, _, _, text in pages)
    sheets = tuple(Sheet(pdf.name, n, number, title, discipline, ("Plans",) if "PLAN" in title else ("Schedules",))
                   for n, number, title, _ in pages)
    return SimpleNamespace(job=job, pages=records, sheets=sheets, sections=(), tags=(), bid=None, flags=())


# ---- 1. Text Layer Detection --------------------------------------------------------------------------------------

def test_has_text_layer_identifies_vector_vs_scanned_sheets(tmp_path):
    # Vector sheet with text
    vector_pdf = make_pdf(tmp_path / "vector.pdf", Page(W, H, ((200, 200, FILLER, 12), (300, 300, "VAV-1", 14))))
    with pymupdf.open(vector_pdf) as doc:
        assert has_text_layer(doc[0]) is True

    # Scanned sheet without text layer (image only)
    scanned_pdf = make_pdf(tmp_path / "scanned.pdf", Page(W, H, scanned="EF-1 EF-2 MECHANICAL PLAN"))
    with pymupdf.open(scanned_pdf) as doc:
        assert has_text_layer(doc[0]) is False

    # Completely blank page
    blank_pdf = make_pdf(tmp_path / "blank.pdf", Page(W, H))
    with pymupdf.open(blank_pdf) as doc:
        assert has_text_layer(doc[0]) is False


# ---- 2. Multi-line / Stacked Tag Extraction in PDF Text Layer -----------------------------------------------------

def test_located_boxes_extracts_stacked_tags(tmp_path):
    # Stacked tag: "VAV" on top line, "1" on line directly below
    texts = (
        (100, 100, FILLER, 10),
        (300, 400, "VAV", 14),
        (300, 415, "1", 14),
        (500, 500, "EF-2", 14),
    )
    pdf = make_pdf(tmp_path / "stacked.pdf", Page(W, H, texts))
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        found = located_boxes(page, r"VAV-\d+", scale=1.0)
        tags = [t for t, _ in found]
        assert "VAV-1" in tags
        # Box should enclose both "VAV" and "1"
        vav_box = next(b for t, b in found if t == "VAV-1")
        assert vav_box[2] > 0 and vav_box[3] > 0


# ---- 3. Tag Classification (Confident vs Ambiguous) ---------------------------------------------------------------

def test_classify_located_boxes_differentiates_confident_and_ambiguous(tmp_path):
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1", 14),                             # clean, isolated tag -> confident
        (600, 400, "VAV", 14),                              # stacked tag -> ambiguous
        (600, 415, "2", 14),
        (900, 500, "(EF-3?)", 14),                          # tag surrounded by punctuation -> ambiguous
    )
    pdf = make_pdf(tmp_path / "tags.pdf", Page(W, H, texts))
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        confident, ambiguous = classify_located_boxes(page, r"(?:EF-\d+|VAV-\d+)", scale=1.0)
        conf_tags = [t for t, _ in confident]
        amb_tags = [t for t, _, _ in ambiguous]

        assert "EF-1" in conf_tags
        assert "VAV-2" in amb_tags
        assert any(t == "EF-3" for t in amb_tags)


# ---- 4. Micro-Crops for Ambiguous Tags ----------------------------------------------------------------------------

def test_cut_micro_crops_generates_small_crops_around_ambiguous_boxes(tmp_path):
    # Create a 2400x1600 sheet picture
    sheet_pic = tmp_path / "sheet.png"
    img = Image.new("RGB", (2400, 1600), color=(255, 255, 255))
    img.save(sheet_pic)

    ambiguous_boxes = [
        (400, 500, 80, 40),
        (1800, 1200, 90, 45),
    ]
    crops = cut_micro_crops(sheet_pic, ambiguous_boxes, margin=50, min_size=200, max_size=400)
    assert len(crops) == 2

    for (cx, cy, cw, ch), path in crops:
        assert path.exists()
        assert 200 <= cw <= 400
        assert 200 <= ch <= 400
        with Image.open(path) as crop_img:
            assert crop_img.size == (cw, ch)


# ---- 5. Image Token Savings Calculation ---------------------------------------------------------------------------

def test_token_savings_shows_massive_reduction_on_micro_crops():
    sheet_size = (3000, 2000)
    # A full sheet tiled with 1568x1568 tiles (overlap 192)
    grid = tile_grid(sheet_size[0], sheet_size[1])
    full_tokens = sum(image_tokens(w, h) for _, _, w, h in grid)

    # 2 ambiguous tags cropped to 300x300 px
    crops = [(400, 400, 300, 300), (1200, 800, 300, 300)]
    crop_tokens = sum(image_tokens(w, h) for _, _, w, h in crops)

    savings = token_savings(sheet_size, crops)
    assert savings["full_sheet_tokens"] == full_tokens
    assert savings["micro_crop_tokens"] == crop_tokens
    assert savings["tokens_saved"] > 0
    assert savings["savings_pct"] >= 90.0   # Over 90% image tokens saved!


# ---- 6. Hybrid Vision Question (One Request Per Sheet) -------------------------------------------------------------

class MockTransport:
    def __init__(self, answer_tags: list[tuple[str, int, int, int, int]] | None = None,
                 untagged_counts: dict[str, int] | None = None):
        self.answer_tags = answer_tags or []
        self.untagged_counts = untagged_counts or {}
        self.asked: list[dict] = []
        self.waiting = 0
        self.last_error = None

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append({
            "kind": kind, "name": name, "prompt": prompt, "extra": extra,
            "images": tuple(images), "schema": schema,
        })
        patterns = extra.get("patterns", [])
        tiles = extra.get("tiles", [])
        ans_patterns = []
        for p in patterns:
            found = []
            for tag, x, y, w, h in self.answer_tags:
                if re.fullmatch(p, tag):
                    # Find which tile/crop contains this box
                    for n, (tx, ty, tw, th) in enumerate(tiles, start=1):
                        if x >= tx and y >= ty and x + w <= tx + tw and y + h <= ty + th:
                            found.append({"text": tag, "count": 1,
                                          "boxes": [{"tile": n, "x": x - tx, "y": y - ty, "width": w, "height": h}]})
            ans_patterns.append({
                "pattern": p,
                "tiles_examined": list(range(1, len(tiles) + 1)),
                "tags": found,
                "untagged_symbols": self.untagged_counts.get(p, 0),
            })
        return {"patterns": ans_patterns}


def test_cross_check_sends_only_micro_crops_for_ambiguous_tags(tmp_path):
    # Sheet has 1 confident tag (EF-1) and 1 ambiguous stacked tag (EF-2)
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1", 14),
        (600, 400, "EF", 14),
        (600, 415, "2", 14),
    )
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])

    # Vision mock verifies EF-2 in the micro-crop
    # In whole-sheet pixels at 150 dpi (W=1728 pt -> 3600 px, scale ~2.083)
    transport = MockTransport(answer_tags=[("EF-2", 1250, 850, 60, 30)])
    cache = tmp_path / "cache"

    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1", "EF-2"), count=Count(2)),)),
    ))

    checked = counts.cross_check(job, cat, cache, transport=transport)
    assert len(transport.asked) == 1
    asked = transport.asked[0]
    # Verify ONLY micro-crops were sent, NOT the 6 full tiles
    assert len(asked["images"]) == 1
    assert "micro-crop" in asked["prompt"].lower() or "crop" in asked["prompt"].lower()

    ef = checked.system("EF").families[0].count
    assert ef.value == 2


# ---- 7. Fallback to Full Tiles on Sheets Without Text Layer --------------------------------------------------------

def test_cross_check_falls_back_to_full_tiles_for_scanned_sheet(tmp_path):
    # Scanned sheet: no text layer
    pdf = make_pdf(tmp_path / "job" / "Scanned.pdf", Page(W, H, scanned="EF-1 EF-2 ON PLAN"))
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "")])

    transport = MockTransport(answer_tags=[("EF-1", 200, 200, 50, 20), ("EF-2", 500, 200, 50, 20)])
    cache = tmp_path / "cache"

    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1", "EF-2"), count=Count(2)),)),
    ))

    checked = counts.cross_check(job, cat, cache, transport=transport)
    assert len(transport.asked) == 1
    asked = transport.asked[0]
    # Scanned page sends the full tile grid (multiple tiles covering entire sheet)
    assert len(asked["images"]) > 1
    assert len(asked["extra"]["tiles"]) > 1


# ---- 8. Schedule Expects Untagged Symbols --------------------------------------------------------------------------

def test_cross_check_asks_for_untagged_symbols_when_schedule_exceeds_text_count(tmp_path):
    # Plan text layer has only 1 tag (EF-1)
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1", 14),
    )
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])

    # Schedule says there are 3 EF units (so 2 untagged symbols expected)
    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1",), count=Count(3)),)),
    ))

    transport = MockTransport(untagged_counts={"EF-[0-9]+": 2})
    cache = tmp_path / "cache"

    checked = counts.cross_check(job, cat, cache, transport=transport)
    assert len(transport.asked) == 1
    asked = transport.asked[0]
    assert "symbols" in asked["prompt"].lower() or "untagged" in asked["prompt"].lower()


def test_a_confident_match_does_not_ask_the_vision_model(tmp_path):
    # One tag, alone on a short line, and the schedule names that same count. Nothing is ambiguous and nothing is missing.
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1", 14),
    )
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "EF-1")])
    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1",), count=Count(1)),)),
    ))
    transport = MockTransport()
    checked = counts.cross_check(job, cat, tmp_path / "cache", transport=transport)
    assert transport.asked == []
    assert checked.system("EF").families[0].count.value == 1


# ---- CNT-6: the crop answer stays out of the picture count -------------------------------------------------------

EF3_ONLY_IN_PICTURE = ("EF-3", 2500, 1500, 80, 25)     # drawn in the sheet picture only, in its pixels


def _ef_sheet(tmp_path):
    """EF-1 clean, "(EF-2)" ambiguous in the text layer (150 dpi picture: 1 pt is 150/72 px)."""
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1", 14),
        (600, 400, "(EF-2)", 14),
    )
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    with pymupdf.open(pdf) as doc:
        confident, ambiguous = classify_located_boxes(doc[0], r"EF-[0-9]+", scale=1.0)
    assert [t for t, _ in confident] == ["EF-1"]
    assert [t for t, _, _ in ambiguous] == ["EF-2"]
    return pdf, _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])


def _ef_job(value):
    return Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1", "EF-2", "EF-3"), count=Count(value)),)),
    ))


def test_a_sheet_short_of_the_schedule_asks_the_full_tiles_even_with_an_ambiguous_box(tmp_path):
    _pdf, cat = _ef_sheet(tmp_path)
    transport = MockTransport(answer_tags=[("EF-2", 1255, 815, 80, 25), EF3_ONLY_IN_PICTURE])
    cache = tmp_path / "cache"
    checked = counts.cross_check(_ef_job(3), cat, cache, transport=transport)

    assert len(transport.asked) == 1
    asked = transport.asked[0]
    assert not asked["extra"].get("is_crops")
    assert len(asked["extra"]["tiles"]) > 1
    [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    assert "EF-3" in proof["vision_tags"]
    assert set(proof["vision_tags"]) <= {"EF-2", "EF-3"}        # only what the transport returned
    assert proof["vision"] == 2
    assert proof["located_tags"] == ["EF-1", "EF-2"]
    count = checked.system("EF").families[0].count
    assert count.value == 3


def test_a_crop_answer_is_never_stored_as_the_picture_count(tmp_path):
    _pdf, cat = _ef_sheet(tmp_path)
    transport = MockTransport(answer_tags=[("EF-2", 1255, 815, 80, 25)])
    cache = tmp_path / "cache"
    checked = counts.cross_check(_ef_job(2), cat, cache, transport=transport)

    assert len(transport.asked) == 1 and transport.asked[0]["extra"].get("is_crops")
    [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    assert proof["vision"] is None and proof["vision_tags"] == []
    assert proof["located_tags"] == ["EF-1", "EF-2"]          # the crop confirmed the ambiguous box
    count = checked.system("EF").families[0].count
    refs = [*count.sources, *(o.ref for o in count.others)]
    assert all(r.quote != counts.SEEN_QUOTE for r in refs)
    assert count.value == 2 and not count.others


def test_a_crop_answer_that_does_not_read_the_ambiguous_tag_drops_it_from_the_located_count(tmp_path):
    _pdf, cat = _ef_sheet(tmp_path)
    transport = MockTransport(answer_tags=[])                  # the crop shows no EF tag
    cache = tmp_path / "cache"
    checked = counts.cross_check(_ef_job(2), cat, cache, transport=transport)

    assert len(transport.asked) == 1 and transport.asked[0]["extra"].get("is_crops")
    [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    assert proof["located_tags"] == ["EF-1"] and proof["vision"] is None
    count = checked.system("EF").families[0].count
    assert count.value == 2
    assert [(o.value, o.ref.quote) for o in count.others] == [(1, counts.LOCATED_QUOTE)]


# ---- CNT-8: a raster plan with a vector title block ----------------------------------------------------------------

TITLE_BLOCK = "M-101 FIRST FLOOR PLAN - MECHANICAL. ISSUED FOR BID. DRAWN BY AB, CHECKED BY CD. SCALE 1/8 IN = 1 FT"


def test_a_scanned_plan_with_a_vector_title_block_is_counted_on_the_full_tiles(tmp_path):
    assert len(TITLE_BLOCK) >= 50 and not re.search(r"EF-[0-9]+", TITLE_BLOCK)
    pdf = make_pdf(tmp_path / "job" / "Scanned.pdf",
                   Page(W, H, ((1200, 1100, TITLE_BLOCK, 8),), scanned="EF-1 EF-2 ON PLAN"))
    with pymupdf.open(pdf) as doc:
        assert has_text_layer(doc[0]) is True
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", TITLE_BLOCK)])
    transport = MockTransport(answer_tags=[("EF-1", 200, 200, 50, 20), ("EF-2", 500, 200, 50, 20)])
    cache = tmp_path / "cache"
    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1", "EF-2"), count=Count(None)),)),
    ))
    checked = counts.cross_check(job, cat, cache, transport=transport)

    assert len(transport.asked) == 1
    asked = transport.asked[0]
    assert not asked["extra"].get("is_crops")
    assert len(asked["extra"]["tiles"]) > 1
    count = checked.system("EF").families[0].count
    assert count.value == 2
    assert [r.quote for r in count.sources] == [counts.SEEN_QUOTE]


def test_a_vector_plan_with_no_tags_is_not_asked(tmp_path):
    texts = ((100, 100, FILLER, 10), (1200, 1100, TITLE_BLOCK, 8))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    cat = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    transport = MockTransport(answer_tags=[("EF-1", 200, 200, 50, 20)])
    job = Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1",), count=Count(None)),)),
    ))
    checked = counts.cross_check(job, cat, tmp_path / "cache", transport=transport)
    assert transport.asked == []
    assert checked.system("EF").families[0].count.value is None


# ---- CNT-4: a tag and the number below it are not one longer tag ---------------------------------------------------

def test_a_tag_over_a_number_line_is_not_joined_into_a_longer_tag(tmp_path):
    texts = (
        (100, 100, FILLER, 10),
        (300, 300, "EF-1\n450 CFM", 14),                    # a tag over its airflow: EF-1, never EF-1-450
        (700, 300, "EF-2\n12", 14),                         # a tag over a bare number: EF-2, never EF-2-12
        (300, 600, "VAV", 14),                              # a bubble: VAV over 1 is VAV-1
        (300, 615, "1", 14),
    )
    pdf = make_pdf(tmp_path / "stacked.pdf", Page(W, H, texts))
    with pymupdf.open(pdf) as doc:
        assert sorted({t for t, _ in located_boxes(doc[0], r"EF-\d+(?:-\d+)*", scale=1.0)}) == ["EF-1", "EF-2"]
        assert {t for t, _ in located_boxes(doc[0], r"VAV-\d+", scale=1.0)} == {"VAV-1"}


# ---- CNT-9: the picture count is told no expected number; untagged symbols are their own count -------------------

def _ef1_sheet(tmp_path):
    texts = ((100, 100, FILLER, 10), (300, 300, "EF-1", 14))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    return _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])


def _ef1_job(value):
    return Job(name="26-9999", systems=(
        System(key="EF", name="Exhaust Fan", shape="Exhaust Fan", control="none",
               families=(Family(name="Exhaust Fan", tags=("EF-1",), count=Count(value)),)),
    ))


def test_the_whole_sheet_question_holds_no_expected_number(tmp_path):
    asked = []
    for value in (3, 30):
        transport = MockTransport()
        counts.cross_check(_ef1_job(value), _ef1_sheet(tmp_path / str(value)), tmp_path / str(value) / "cache",
                           transport=transport)
        [question] = transport.asked
        assert not question["extra"].get("is_crops") and len(question["extra"]["tiles"]) > 1
        asked.append(question)
    prompts = [q["prompt"].replace(Path(q["extra"]["picture"]).name, "PICTURE") for q in asked]
    assert prompts[0] == prompts[1]                          # the schedule's count never reaches the question
    assert {k: v for k, v in asked[0]["extra"].items() if k != "picture"} == \
        {k: v for k, v in asked[1]["extra"].items() if k != "picture"}
    assert "symbols_expected" not in asked[0]["extra"]
    assert "expect" not in asked[0]["prompt"].lower()
    assert "untagged" in asked[0]["prompt"].lower()          # a neutral instruction to report them, if any


def test_untagged_symbols_are_their_own_count_in_the_proof(tmp_path):
    from bms.counts_text import family_pattern

    pattern = family_pattern(["EF-1"], {"EF": 1})
    transport = MockTransport(answer_tags=[("EF-1", 620, 620, 80, 30)], untagged_counts={pattern: 2})
    cache = tmp_path / "cache"
    checked = counts.cross_check(_ef1_job(3), _ef1_sheet(tmp_path), cache, transport=transport)
    assert len(transport.asked) == 1 and "untagged_symbols" in json.dumps(transport.asked[0]["schema"])
    [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    assert proof["vision"] == 1 and proof["vision_tags"] == ["EF-1"]
    assert proof["vision_untagged"] == 2                      # its own count, beside the tag count
    count = checked.system("EF").families[0].count
    assert count.value == 3
    seen = [o.value for o in count.others if o.ref.quote == counts.SEEN_QUOTE]
    assert seen == [1]                                        # never added to the tags counted on the picture


def test_count_sheet_reads_untagged_symbols_into_the_result(tmp_path):
    picture = tmp_path / "p.png"
    Image.new("RGB", (800, 600), "white").save(picture)
    transport = MockTransport(answer_tags=[("EF-1", 10, 10, 40, 20)], untagged_counts={"EF-[0-9]+": 4})
    result = counts.count_sheet(picture, ["EF-[0-9]+"], transport=transport)["EF-[0-9]+"]
    assert result.value == 1 and result.untagged == 4
    assert counts.count_tags(picture, "EF-[0-9]+", transport=MockTransport()).untagged == 0
