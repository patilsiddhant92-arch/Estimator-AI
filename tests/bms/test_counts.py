"""Workstream 6: the two plan counts (located on the sheet text, counted on the sheet picture), the cross-check
that records every differing count, and the proof images. Every PDF here is invented in the test."""
from __future__ import annotations

import dataclasses
import inspect
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

from bms import counts
from bms.ai import NoAnswer
from bms.model import Count, Family, Job, OtherCount, Ref, System

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdfs import FILLER, Page, make_pdf  # noqa: E402

from estimator.catalogue.documents import Document  # noqa: E402
from estimator.catalogue.register import PageRecord  # noqa: E402
from estimator.catalogue.sheet_types import Sheet  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_JOB = FIXTURES / "sample_job.json"

W, H = 1728, 1152          # a 24 x 16 inch sheet, in points
PLAN_TEXTS = (
    (200, 200, FILLER, 10),
    (300, 400, "EF-1", 14),
    (900, 300, "EF-2", 14),
    (1500, 900, "EF-3", 14),
    (600, 1000, "EF-4", 14),                                           # on the plan, not in the family's tags
    (300, 700, "EF-1 SHALL BE INTERLOCKED WITH THE MOTORIZED DAMPER ABOVE", 9),   # a note, not a placed tag
    (1200, 600, "RTU-1", 14),
    (1580, 1100, "M-101", 30),
)


# ---- helpers ---------------------------------------------------------------------------------------------------

def _sample_job() -> Job:
    return Job.from_dict(json.loads(SAMPLE_JOB.read_text(encoding="utf-8")))


def _catalogue(pdf: Path, pages: list[tuple[int, str, str, str]], discipline: str = "Mechanical"):
    """A catalogue of one drawing set: pages as (page, sheet number, title, text of the page)."""
    document = Document(pdf, pdf.name, "drawings", "base", len(pages))
    job = SimpleNamespace(name="26-9999", root=pdf.parent, documents=(document,))
    records = tuple(PageRecord(pdf.name, n, "text", text, 0, True) for n, _, _, text in pages)
    sheets = tuple(Sheet(pdf.name, n, number, title, discipline, ("Plans",) if "PLAN" in title else ("Schedules",))
                   for n, number, title, _ in pages)
    return SimpleNamespace(job=job, pages=records, sheets=sheets, sections=(), tags=(), bid=None, flags=())


def _plan(tmp_path: Path, texts=PLAN_TEXTS, rotation: int = 0, name: str = "Drawings.pdf"):
    pdf = make_pdf(tmp_path / "job" / name, Page(W, H, texts, rotation=rotation))
    text = "\n".join(t for _, _, t, _ in texts)
    return pdf, _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", text)])


def _family(job: Job, key: str, name: str) -> Family:
    return next(f for f in job.system(key).families if f.name == name)


class FakeVision:
    """A Transport that 'sees' the given tags at the given places of the whole picture and answers a sheet's one
    question with, for each pattern asked, every tag fitting it lying wholly inside a tile, with its boxes in each
    tile's pixels (plus one tag that does not fit the pattern)."""

    def __init__(self, tags: list[tuple[str, int, int, int, int]], fail_on: int | None = None, omit: tuple = (),
                 skip_tiles: int = 0):
        self.tags = tags
        self.omit = omit
        self.fail_on = fail_on
        self.skip_tiles = skip_tiles        # how many answers (the first ones) look at the first tile only
        self.asked: list[dict] = []
        self.waiting = 0
        self.last_error = None

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append({"kind": kind, "name": name, "prompt": prompt, "extra": extra, "images": tuple(images),
                           "schema": schema, "instructions": instructions})
        if self.fail_on is not None and len(self.asked) == self.fail_on:
            self.waiting += 1
            raise NoAnswer("waiting for the chat", waiting=True)
        examined = list(range(1, len(extra["tiles"]) + 1))
        if len(self.asked) <= self.skip_tiles:
            examined = [1]                  # looked at one picture only
        answer = []
        for pattern in extra["patterns"]:
            if any(o in pattern for o in self.omit):
                continue          # this answer leaves the pattern out
            tags: dict[str, list[dict]] = {}
            for text, x, y, tw, th in self.tags:
                if not re.fullmatch(pattern, text.replace(" ", "-")):
                    continue
                for n, (x0, y0, w, h) in enumerate(extra["tiles"], start=1):
                    if x >= x0 and y >= y0 and x + tw <= x0 + w and y + th <= y0 + h:
                        tags.setdefault(text, []).append(
                            {"tile": n, "x": x - x0, "y": y - y0, "width": tw, "height": th})
            found = [{"text": t, "count": len(b), "boxes": b} for t, b in tags.items()]
            found.append({"text": "ZZ-9", "count": 1, "boxes": [{"tile": 1, "x": 1, "y": 1, "width": 5, "height": 5}]})
            answer.append({"pattern": pattern, "tiles_examined": examined, "tags": found})
        return {"patterns": answer}


class Refusable(FakeVision):
    """A FakeVision with the transport's `refuse`: True like the API (asked again now), False like the chat."""

    def __init__(self, *args, again: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.again = again
        self.refused: list[str] = []

    def refuse(self, problem: str) -> bool:
        self.refused.append(problem)
        return self.again


def _blank_picture(path: Path, size=(3600, 2400)) -> Path:
    Image.new("RGB", size, "white").save(path)
    return path


# ---- the contract ------------------------------------------------------------------------------------------------

def test_transport_is_an_optional_keyword():
    for function in (counts.count_tags, counts.cross_check):
        parameter = inspect.signature(function).parameters["transport"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None


# ---- count_tags (the vision count) ------------------------------------------------------------------------------

def test_count_tags_never_raises_on_an_unreadable_picture(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a picture")
    vision = FakeVision([])
    assert counts.count_tags(broken, "EF-[0-9]+", transport=vision) == counts.CountResult(None, ())
    assert counts.count_tags(tmp_path / "missing.png", "EF-[0-9]+", transport=vision) == counts.CountResult(None, ())
    assert counts.count_tags(_blank_picture(tmp_path / "p.png"), "EF-[", transport=vision) == counts.CountResult(None, ())


def test_count_tags_without_a_transport_cannot_count(tmp_path):
    assert counts.count_tags(_blank_picture(tmp_path / "p.png"), "EF-[0-9]+") == counts.CountResult(None, ())


def test_count_tags_counts_each_tag_once_over_tiles_in_one_question(tmp_path):
    picture = _blank_picture(tmp_path / "p.png")
    seen = [("EF-1", 100, 100, 80, 30), ("EF-2", 1500, 200, 80, 30),      # EF-2 lies in the overlap of two tiles
            ("EF 3", 3000, 2000, 80, 30), ("EF-3", 3300, 2200, 80, 30),    # the same tag twice: counted once
            ("RTU-1", 2000, 1000, 90, 30)]                                 # another family's tag
    vision = FakeVision(seen)
    result = counts.count_tags(picture, "EF-[0-9]+", transport=vision)
    assert result.value == 3 == len(result.boxes)
    assert [b.text for b in result.boxes] == ["EF-1", "EF-2", "EF-3"]
    assert result.boxes[1] == counts.Box(1500, 200, 80, 30, "EF-2")        # back in the whole picture's pixels
    [asked] = vision.asked                                                 # one question for the whole sheet
    assert asked["kind"] == counts.COUNT_TAGS and len(asked["images"]) > 1  # every tile, as its own picture
    assert len(asked["images"]) == len(asked["extra"]["tiles"])
    assert all(Path(i).exists() for i in asked["images"])
    assert "EF-[0-9]+" in asked["prompt"]
    for n, (x, y, w, h) in enumerate(asked["extra"]["tiles"], start=1):    # each tile's place stated, in order
        assert f"Tile {n}: x {x}, y {y}, {w} x {h} pixels" in asked["prompt"]
    for image in asked["images"]:
        with Image.open(image) as tile:
            assert max(tile.size) <= counts.TILE


def test_one_question_per_sheet_counts_every_family_on_it(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (3000, 1500))           # three tiles side by side
    seen = [("EF-1", 100, 100, 80, 30), ("EF-2", 2800, 1200, 80, 30), ("RTU-1", 1400, 700, 90, 30),
            ("RTU-2", 2900, 100, 90, 30)]
    vision = FakeVision(seen)
    found = counts.count_sheet(picture, ["EF-[0-9]+", "RTU-[0-9]+"], transport=vision)
    [asked] = vision.asked
    assert len(asked["images"]) == 3 and "EF-[0-9]+" in asked["prompt"] and "RTU-[0-9]+" in asked["prompt"]
    assert found["EF-[0-9]+"].value == 2 and found["RTU-[0-9]+"].value == 2
    assert [b.text for b in found["RTU-[0-9]+"].boxes] == ["RTU-1", "RTU-2"]
    assert found["RTU-[0-9]+"].boxes[1] == counts.Box(2900, 100, 90, 30, "RTU-2")


def test_cross_check_asks_one_question_for_a_three_tile_sheet_with_two_families(tmp_path):
    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (600, 300, "EF-2", 14), (500, 500, "RTU-1", 14))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1440, 720, texts))      # 3000 x 1500 at 150 dpi
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    seen = [("EF-1", 625, 800, 90, 35), ("EF-2", 1460, 600, 90, 35), ("EF-3", 2700, 600, 90, 35),
            ("RTU-1", 1040, 1000, 90, 35), ("RTU-2", 2800, 1300, 90, 35), ("RTU-3", 100, 1300, 90, 35)]
    vision = FakeVision(seen)
    cache = tmp_path / "cache"
    checked = counts.cross_check(_sample_job(), catalogue, cache, transport=vision)
    [asked] = vision.asked                                                 # one question for the sheet
    assert len(asked["images"]) == 3 and len(asked["extra"]["tiles"]) == 3
    assert any("EF" in p for p in asked["extra"]["patterns"]) and any("RTU" in p for p in asked["extra"]["patterns"])
    ef = _family(checked, "EF", "Exhaust Fan").count
    rtu = _family(checked, "RTU", "Rooftop Unit").count
    assert ef.value == 3 and ef.sources[-1].quote == "counted on the sheet picture"
    assert rtu.value == 3 and rtu.sources[-1].quote == "counted on the sheet picture"
    assert any(o.value == 1 and o.ref.quote == "located on the sheet text" for o in rtu.others)
    [ef_proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    [rtu_proof] = counts.proofs_for(cache, "RTU", "Rooftop Unit")
    assert ef_proof["vision"] == 3 and ef_proof["vision_tags"] == ["EF-1", "EF-2", "EF-3"]
    assert rtu_proof["vision"] == 3 and rtu_proof["vision_tags"] == ["RTU-1", "RTU-2", "RTU-3"]
    assert {"x": 2800, "y": 1300, "width": 90, "height": 35, "text": "RTU-2"} in rtu_proof["vision_boxes"]
    assert Path(ef_proof["proof"]).exists() and Path(rtu_proof["proof"]).exists()


def test_a_pattern_the_answer_leaves_out_gets_no_vision_count(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (3000, 1500))
    seen = [("EF-1", 100, 100, 80, 30), ("EF-2", 2800, 1200, 80, 30), ("RTU-1", 1400, 700, 90, 30)]
    found = counts.count_sheet(picture, ["EF-[0-9]+", "RTU-[0-9]+"], transport=FakeVision(seen, omit=("RTU",)))
    assert found["EF-[0-9]+"].value == 2 and "RTU-[0-9]+" not in found
    assert counts.count_tags(picture, "RTU-[0-9]+", transport=FakeVision(seen, omit=("RTU",))).value is None

    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (600, 300, "EF-2", 14), (500, 500, "RTU-1", 14))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1440, 720, texts))
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    seen = [("EF-1", 625, 800, 90, 35), ("EF-2", 1460, 600, 90, 35), ("EF-3", 2700, 600, 90, 35),
            ("RTU-1", 1040, 1000, 90, 35), ("RTU-2", 2800, 1300, 90, 35)]
    before = _sample_job()
    cache = tmp_path / "cache"
    checked = counts.cross_check(before, catalogue, cache, transport=FakeVision(seen, omit=("RTU",)))
    assert _family(checked, "EF", "Exhaust Fan").count.value == 3
    rtu = _family(checked, "RTU", "Rooftop Unit")
    assert not any(o.ref.quote == "counted on the sheet picture" for o in rtu.count.others)
    assert not any(r.quote == "counted on the sheet picture" for r in rtu.count.sources)
    text_only = counts.cross_check(before, catalogue, tmp_path / "cache2")      # the sheet text alone, no vision
    assert rtu == _family(text_only, "RTU", "Rooftop Unit")                  # the vision pass added nothing to RTU
    assert checked.system("RTU").devices == text_only.system("RTU").devices
    [rtu_proof] = counts.proofs_for(cache, "RTU", "Rooftop Unit")
    assert rtu_proof["vision"] is None and rtu_proof["vision_tags"] == []


def test_count_tags_gives_no_count_without_an_answer(tmp_path):
    picture = _blank_picture(tmp_path / "p.png")
    vision = FakeVision([("EF-1", 100, 100, 80, 30)], fail_on=1)
    assert counts.count_tags(picture, "EF-[0-9]+", transport=vision) == counts.CountResult(None, ())
    assert vision.waiting == 1 and len(vision.asked) == 1


def test_count_tags_drops_a_box_outside_its_tile(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (800, 600))

    class Wild(FakeVision):
        def ask(self, *args, **kwargs):
            super().ask(*args, **kwargs)
            return {"patterns": [{"pattern": "EF-[0-9]+", "tiles_examined": [1], "tags": [
                {"text": "EF-1", "count": 1, "boxes": [{"tile": 1, "x": 5000, "y": 10, "width": 10, "height": 10}]},
                {"text": "EF-3", "count": 1, "boxes": [{"tile": 7, "x": 10, "y": 10, "width": 10, "height": 10}]},
                {"text": "EF-2", "count": 1, "boxes": [{"tile": 1, "x": 10, "y": 10, "width": 40, "height": 20}]}]}]}

    result = counts.count_tags(picture, "EF-[0-9]+", transport=Wild([]))
    assert [b.text for b in result.boxes] == ["EF-2"]


def test_count_tags_refuses_an_answer_that_breaks_the_schema(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (800, 600))

    class Bad(FakeVision):
        def ask(self, *args, **kwargs):
            super().ask(*args, **kwargs)
            return {"tags": [{"text": "EF-1", "x": "left"}]}

    assert counts.count_tags(picture, "EF-[0-9]+", transport=Bad([])) == counts.CountResult(None, ())


# ---- the located-text count and cross_check without vision ----------------------------------------------------

def test_cross_check_records_the_located_text_count(tmp_path):
    pdf, catalogue = _plan(tmp_path)
    job = _sample_job()
    checked = counts.cross_check(job, catalogue, tmp_path / "cache")

    ef = _family(checked, "EF", "Exhaust Fan").count
    # EF-1 to EF-4 are placed on the plan (EF-4 is not among the family's tags, but EF is this family's prefix
    # alone); the note naming EF-1 is not a placed tag. The higher count prints; the planner's 3 is kept.
    assert ef.value == 4
    [source] = ef.sources
    assert source.quote == "located on the sheet text" and source.where == "M-101, Drawings.pdf page 1"
    assert OtherCount(3, Ref("S6", "EF-1 EF-2 EF-3", "M-001, Drawings.pdf page 1")) in ef.others

    rtu = _family(checked, "RTU", "Rooftop Unit").count
    assert rtu.value == 2                                     # never lowered by the plan's 1
    assert [o.value for o in rtu.others].count(1) == 2        # the planner's other count and the plan's own
    assert any(o.ref.quote == "located on the sheet text" for o in rtu.others)

    # families whose tags are on no plan are left as they are
    assert checked.system("VRF") == job.system("VRF") and checked.system("DH") == job.system("DH")
    assert checked.system("CUH") == job.system("CUH")


def test_cross_check_flags_the_devices_counted_from_the_changed_family(tmp_path):
    _, catalogue = _plan(tmp_path)
    job = _sample_job()
    checked = counts.cross_check(job, catalogue, tmp_path / "cache")
    before = {d.id: d for d in job.system("EF").devices}
    for device in checked.system("EF").devices:
        uses_family = any(r.source_id == "S6" for r in before[device.id].quantity.sources)
        if uses_family:
            assert device.flag == "quantity"
        else:
            assert device.flag == before[device.id].flag
        assert device.quantity == before[device.id].quantity      # quantities are the writer's, never changed here


def test_cross_check_is_idempotent(tmp_path):
    _, catalogue = _plan(tmp_path)
    once = counts.cross_check(_sample_job(), catalogue, tmp_path / "cache")
    assert counts.cross_check(once, catalogue, tmp_path / "cache") == once


def test_cross_check_writes_proof_images(tmp_path):
    _, catalogue = _plan(tmp_path)
    cache = tmp_path / "cache"
    counts.cross_check(_sample_job(), catalogue, cache)
    proofs = counts.load_proofs(cache)
    ef = [p for p in proofs if p["system_key"] == "EF" and p["family"] == "Exhaust Fan"]
    assert len(ef) == 1
    proof = ef[0]
    assert proof["sheet"] == "M-101, Drawings.pdf page 1"
    assert proof["located_text"] == 4 and proof["vision"] is None
    assert proof["located_tags"] == ["EF-1", "EF-2", "EF-3", "EF-4"]
    image = Path(proof["proof"])
    assert image.exists() and image.is_relative_to(cache.resolve())
    with Image.open(image) as picture:
        assert picture.size[0] > 50 and picture.size[1] > 50
        colours = picture.convert("RGB").getcolors(1_000_000)
        assert any(r > 180 and g < 80 and b < 80 for _, (r, g, b) in colours)    # the located boxes, drawn red
    assert counts.proofs_for(cache, "EF", "Exhaust Fan") == ef


def test_located_boxes_sit_on_the_tags_on_a_rotated_sheet(tmp_path):
    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 24), (1500, 900, "EF-2", 24))
    for rotation in (0, 90):
        folder = tmp_path / f"r{rotation}"
        _, catalogue = _plan(folder, texts=texts, rotation=rotation)
        cache = folder / "cache"
        counts.cross_check(_sample_job(), catalogue, cache)
        [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
        assert proof["located_text"] == 2
        with Image.open(proof["picture"]) as sheet:
            grey = sheet.convert("L")
            for box in proof["located_boxes"]:
                assert 0 <= box["x"] and box["x"] + box["width"] <= sheet.size[0]
                assert 0 <= box["y"] and box["y"] + box["height"] <= sheet.size[1]
                inside = grey.crop((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]))
                assert inside.getextrema()[0] < 100, (rotation, box)       # ink under every box


def test_a_shared_prefix_counts_only_the_family_s_own_tags(tmp_path):
    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-2", 14), (1500, 900, "EF-7", 14),
             (600, 1000, "EF-8", 14), (700, 1000, "EF-9", 14))
    _, catalogue = _plan(tmp_path, texts=texts)
    ref = Ref("S1", "EF-1 EF-2", "M-001, Drawings.pdf page 1")
    a = System("EFA", "Exhaust Fans A", "Exhaust Fan", "field",
               (Family("Exhaust Fan", ("EF-1", "EF-2"), Count(2, (ref,))),))
    b = System("EFB", "Exhaust Fans B", "Exhaust Fan", "field",
               (Family("Exhaust Fan", ("EF-7", "EF-8"), Count(2, (Ref("S2", "EF-7 EF-8", "M-001"),))),))
    checked = counts.cross_check(Job("t", (a, b)), catalogue, tmp_path / "cache")
    assert checked.system("EFA").families[0].count == Count(2, (ref, Ref(
        "C1", "located on the sheet text", "M-101, Drawings.pdf page 1")))
    assert checked.system("EFB").families[0].count.value == 2             # EF-9 belongs to neither: not counted


def test_an_unknown_count_takes_the_plan_count(tmp_path):
    _, catalogue = _plan(tmp_path)
    system = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", ("EF-1",), Count(None)),))
    checked = counts.cross_check(Job("t", (system,)), catalogue, tmp_path / "cache")
    count = checked.system("EF").families[0].count
    assert count.value == 4 and count.others == () and count.sources[0].quote == "located on the sheet text"


def test_cross_check_never_raises_on_an_unreadable_document(tmp_path):
    pdf = tmp_path / "job" / "Drawings.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 broken")
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "EF-1 EF-2 EF-3 EF-4")])
    job = _sample_job()
    assert counts.cross_check(job, catalogue, tmp_path / "cache") == job
    gone = _catalogue(tmp_path / "nowhere.pdf", [(1, "M-101", "FIRST FLOOR PLAN", "EF-1 EF-2 EF-3 EF-4")])
    assert counts.cross_check(job, gone, tmp_path / "cache") == job
    assert counts.cross_check(job, SimpleNamespace(), tmp_path / "cache") == job


def test_only_plan_sheets_of_the_controls_disciplines_are_counted(tmp_path):
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, PLAN_TEXTS), Page(W, H, PLAN_TEXTS),
                   Page(W, H, PLAN_TEXTS))
    text = "\n".join(t for _, _, t, _ in PLAN_TEXTS)
    catalogue = _catalogue(pdf, [(1, "M-601", "SCHEDULES", text), (2, "M-101", "FIRST FLOOR PLAN", text),
                                 (3, "E-101", "POWER PLAN", text)])
    catalogue.sheets = (catalogue.sheets[0], catalogue.sheets[1], dataclasses.replace(catalogue.sheets[2],
                                                                                       discipline="Electrical"))
    cache = tmp_path / "cache"
    counts.cross_check(_sample_job(), catalogue, cache)
    assert {p["sheet"] for p in counts.load_proofs(cache)} == {"M-101, Drawings.pdf page 2"}


def test_the_count_is_of_different_tags_over_every_plan_sheet(tmp_path):
    first = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-2", 14))
    second = ((200, 200, FILLER, 10), (300, 400, "EF-2", 14), (900, 300, "EF-5", 14))   # EF-2 shown again
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, first), Page(W, H, second))
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "EF-1 EF-2"),
                                 (2, "M-102", "SECOND FLOOR PLAN", "EF-2 EF-5")])
    checked = counts.cross_check(_sample_job(), catalogue, tmp_path / "cache")
    ef = _family(checked, "EF", "Exhaust Fan").count
    assert ef.value == 3 and ef.sources[1].where == ("M-101, Drawings.pdf page 1; M-102, Drawings.pdf page 2")
    assert ef.others == ()                                                 # agrees with the planner's 3
    assert [r.source_id for r in ef.sources] == ["S6", "C1"]


# ---- cross_check with vision ----------------------------------------------------------------------------------

def test_cross_check_with_vision_records_both_counts(tmp_path):
    _, catalogue = _plan(tmp_path)
    scale = 150 / 72
    seen = [(f"EF-{n}", int(x * scale), int((y - 14) * scale), 90, 35)
            for n, (x, y) in enumerate([(300, 400), (900, 300), (1500, 900), (600, 1000), (1000, 1000)], start=1)]
    vision = FakeVision(seen)
    cache = tmp_path / "cache"
    checked = counts.cross_check(_sample_job(), catalogue, cache, transport=vision)
    ef = _family(checked, "EF", "Exhaust Fan").count
    assert ef.value == 5
    assert ef.sources[0].quote == "counted on the sheet picture"
    assert ef.sources[0].where == "M-101 whole sheet, Drawings.pdf page 1 (picture)"
    assert sorted((o.value, o.ref.quote) for o in ef.others) == [
        (3, "EF-1 EF-2 EF-3"), (4, "located on the sheet text")]
    assert len({o.ref.source_id for o in ef.others} | {ef.sources[0].source_id}) == 3
    [proof] = counts.proofs_for(cache, "EF", "Exhaust Fan")
    assert proof["vision"] == 5 and proof["located_text"] == 4
    assert proof["vision_tags"] == ["EF-1", "EF-2", "EF-3", "EF-4", "EF-5"]
    with Image.open(proof["proof"]) as picture:
        colours = picture.convert("RGB").getcolors(1_000_000)
        assert any(b > 180 and r < 80 and g < 120 for _, (r, g, b) in colours)    # the vision boxes, drawn blue
    # one vision question per sheet picture, for every family on it at once
    [asked] = vision.asked
    assert asked["extra"]["picture"] == proof["picture"]
    assert re.search("EF", asked["prompt"]) and re.search("RTU", asked["prompt"])


def test_cross_check_waiting_vision_keeps_the_text_count(tmp_path):
    _, catalogue = _plan(tmp_path)
    vision = FakeVision([], fail_on=1)
    checked = counts.cross_check(_sample_job(), catalogue, tmp_path / "cache", transport=vision)
    ef = _family(checked, "EF", "Exhaust Fan").count
    assert ef.value == 4 and all(o.ref.quote != "counted on the sheet picture" for o in ef.others)
    assert vision.waiting == 1


# ---- every tile examined ----------------------------------------------------------------------------------------

def test_the_count_question_demands_every_tile_be_examined(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (3000, 1500))           # three tiles
    vision = FakeVision([("EF-1", 100, 100, 80, 30)])
    counts.count_tags(picture, "EF-[0-9]+", transport=vision)
    [asked] = vision.asked
    entry = asked["schema"]["properties"]["patterns"]["items"]
    assert "tiles_examined" in entry["required"]
    assert entry["properties"]["tiles_examined"]["items"]["type"] == "integer"
    assert "every tile" in asked["instructions"].lower() and "tiles_examined" in asked["instructions"]
    assert "all 3 tiles" in asked["prompt"] and "tiles_examined" in asked["prompt"]


def test_an_answer_that_skips_a_tile_is_refused_and_asked_again(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (3000, 1500))
    seen = [("EF-1", 100, 100, 80, 30), ("EF-2", 2800, 1200, 80, 30)]
    api = Refusable(seen, skip_tiles=1, again=True)                      # the first answer opened tile 1 only
    result = counts.count_tags(picture, "EF-[0-9]+", transport=api)
    assert result.value == 2 and len(api.asked) == 2
    [problem] = api.refused
    assert "2, 3" in problem and "tile" in problem
    assert "could not be used" in api.asked[1]["prompt"]                  # asked again with the reason
    assert len(api.asked[1]["images"]) == 3                               # still one question for the sheet

    chat = Refusable(seen, skip_tiles=1, again=False)                     # the chat answers on a later run
    assert counts.count_tags(picture, "EF-[0-9]+", transport=chat) == counts.CountResult(None, ())
    assert len(chat.asked) == 1 and len(chat.refused) == 1

    stubborn = Refusable(seen, skip_tiles=2, again=True)                  # skips again: no count, never a crash
    assert counts.count_tags(picture, "EF-[0-9]+", transport=stubborn) == counts.CountResult(None, ())
    assert len(stubborn.asked) == 2

    plain = FakeVision(seen, skip_tiles=1)                                # a transport that cannot refuse
    assert counts.count_tags(picture, "EF-[0-9]+", transport=plain) == counts.CountResult(None, ())


def test_an_answer_without_tiles_examined_is_unusable(tmp_path):
    picture = _blank_picture(tmp_path / "p.png", (800, 600))

    class Lazy(FakeVision):
        def ask(self, *args, **kwargs):
            answer = super().ask(*args, **kwargs)
            for entry in answer["patterns"]:
                del entry["tiles_examined"]
            return answer

    assert counts.count_tags(picture, "EF-[0-9]+", transport=Lazy([("EF-1", 10, 10, 40, 20)])) == \
        counts.CountResult(None, ())


# ---- the family's tag patterns ----------------------------------------------------------------------------------

LETTER_FAMILIES = {          # invented families: tags as a schedule writes them, the tags they stand for
    "TXF": ("TXF-B", ["TXF-B"]),
    "SPXF": ("SPXF-A, B, C", ["SPXF-A", "SPXF-B", "SPXF-C"]),
    "EUH": ("EUH-1, 2", ["EUH-1", "EUH-2"]),
    "CAC": ("CAC-1.5", ["CAC-1.5"]),
    "ACCU": ("ACCU-12-1 thru 6", [f"ACCU-12-{n}" for n in range(1, 7)]),
    "HRU": ("HRU-3.0", ["HRU-3.0"]),
}


@pytest.mark.parametrize("shared", [False, True])
def test_family_patterns_match_the_family_s_real_tags_and_no_bare_part(shared):
    from bms.counts_text import family_pattern, family_tags, fits, prefix_owners, searcher

    owners = prefix_owners([written] for written, _ in LETTER_FAMILIES.values())
    assert "B" not in owners and "2" not in owners
    if shared:                                    # another family has the same prefixes: only the own tags count
        owners = {prefix: 2 for prefix in owners}
    for prefix, (written, tags) in LETTER_FAMILIES.items():
        assert family_tags([written]) == tags
        pattern = family_pattern([written], owners)
        assert pattern is not None
        for tag in tags:
            assert fits(pattern, tag), (pattern, tag)
            assert [m.group(0) for m in searcher(pattern).finditer(f"SEE {tag} ABOVE")] == [tag], (pattern, tag)
        for bare in ("A", "B", "C", "1", "2", "5", "6", "1.5", "3.0", "12-1"):
            assert not fits(pattern, bare), (pattern, bare)
            assert not searcher(pattern).search(f"ROOM {bare} AND {bare}"), (pattern, bare)
    assert not fits(family_pattern(["EUH-1, 2"], {"EUH": 2}), "EUH-3")      # shared prefix: the own tags only


def test_the_located_text_count_uses_the_expanded_tags(tmp_path):
    from bms.counts_text import fits

    texts = ((200, 200, FILLER, 10), (300, 300, "TXF-B", 14), (500, 300, "SPXF-A", 14), (700, 300, "SPXF-C", 14),
             (300, 500, "B", 14), (500, 500, "2", 14), (700, 500, "EUH-2", 14), (900, 500, "CAC-1.5", 14),
             (300, 700, "ACCU-12-3", 14), (500, 700, "ACCU-12-6", 14), (700, 700, "HRU-3.0", 14))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(W, H, texts))
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    systems = tuple(System(key, key, key, "field", (Family(key, (written,), Count(None)),))
                    for key, (written, _) in LETTER_FAMILIES.items())
    vision = FakeVision([])
    cache = tmp_path / "cache"
    checked = counts.cross_check(Job("t", systems), catalogue, cache, transport=vision)
    expected = {"TXF": 1, "SPXF": 2, "EUH": 1, "CAC": 1, "ACCU": 2, "HRU": 1}
    for key, value in expected.items():
        count = checked.system(key).families[0].count
        assert any(r.quote == "located on the sheet text" and count.value == value for r in count.sources), \
            (key, count)
    assert counts.proofs_for(cache, "SPXF", "SPXF")[0]["located_tags"] == ["SPXF-A", "SPXF-C"]
    [asked] = vision.asked                                       # the vision count asks the same patterns
    assert len(asked["extra"]["patterns"]) == len(LETTER_FAMILIES)
    for pattern in asked["extra"]["patterns"]:
        assert not any(fits(pattern, bare) for bare in ("B", "C", "2"))
