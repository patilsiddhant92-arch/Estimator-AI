"""Schedules pasted onto a sheet as pictures, read by eye (1.1). The judge is a fake: no test touches the network."""
from types import SimpleNamespace

import pymupdf
import pytest

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.catalogue.tags import TagEntry
from estimator.reading.pictures import MAX_EDGE, picture_regions, render_pictures
from estimator.reading.schedules import BY_EYE, read_schedules, schedule_from_cells

DOC = "Mech.pdf"
W, H = 3024, 2160
ANSWER = {"schedules": [{"title": "ELECTRIC HEATER SCHEDULE", "headers": ["TAG", "AREA SERVED", "MODEL", "NOTES"],
                         "rows": [{"cells": ["UH-1 THRU UH-3", "STORAGE", "QMARK MUH0341", "4"]},
                                  {"cells": ["CUH-1", "VESTIBULE 005", "", "1,2"]},
                                  {"cells": ["", "", "", ""]}],
                         "notes": ["6. PROVIDE WITH MANUFACTURER'S 24-VOLT CONTROL TRANSFORMER. UNIT CONTROLLER "
                                   "BY TEMPERATURE CONTROL CONTRACTOR."]}]}


class FakeJudge:
    def __init__(self, answer=ANSWER):
        self.answer, self.calls, self.last_error = answer, [], None
        self.cache_dir = None

    def read_schedule(self, image, sheet, page, title_hint, tiles=()):
        self.calls.append((image, sheet, page, title_hint, tuple(tiles)))
        if self.answer is None:
            self.last_error = "judgement pending — waiting for an answer in the chat"
        return self.answer


def _picture_sheet(tmp_path, boxes=((300, 300, 1300, 800),), rotate=0):
    pdf = pymupdf.open()
    page = pdf.new_page(width=W, height=H)
    page.insert_text((2700, 2100), "H601", fontsize=30)
    for box in boxes:
        picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 200), False)
        picture.set_rect(picture.irect, (255, 255, 255))
        page.insert_image(pymupdf.Rect(box), pixmap=picture, keep_proportion=False)
    if rotate:
        page.set_rotation(rotate)
    path = tmp_path / DOC
    pdf.save(str(path))
    pdf.close()
    return pymupdf.open(str(path))


def _catalogue(text="EXHAUST FAN SCHEDULE\nEF-1 ROOF", tags=()):
    return SimpleNamespace(pages=(PageRecord(DOC, 1, "ocr", text, 0, True),),
                           sheets=(Sheet(DOC, 1, "H601", "HVAC SCHEDULES", "Mechanical", ("Schedules",)),
                                   Sheet(DOC, 2, "H101", "HVAC PLAN", "Mechanical", ("Plans",))),
                           tags=tuple(tags))


def test_a_schedule_given_cell_by_cell_makes_the_same_rows_the_table_reader_makes():
    schedule = schedule_from_cells(" ELECTRIC HEATER SCHEDULE ", ["TAG", "AREA SERVED", "MODEL", "NOTES"],
                                   ANSWER["schedules"][0]["rows"] + [{"TAG": "UH-7", "MODEL": "QMARK"}],
                                   ANSWER["schedules"][0]["notes"], (DOC, 1, "H601"))
    assert [r.tag for r in schedule.rows] == ["UH-1", "UH-2", "UH-3", "CUH-1", "UH-7"]
    assert schedule.rows[0].cells == {"TAG": "UH-1 THRU UH-3", "AREA SERVED": "STORAGE", "MODEL": "QMARK MUH0341",
                                      "NOTES": "4"}
    assert schedule.rows[0].model == "QMARK MUH0341" and schedule.rows[4].model == "QMARK"
    assert (schedule.title, schedule.sheet, schedule.source, schedule.type_only) == (
        "ELECTRIC HEATER SCHEDULE", "H601", BY_EYE, False)
    assert schedule.controls_by == ("UNIT CONTROLLER BY TEMPERATURE CONTROL CONTRACTOR.",)


def test_a_schedule_of_types_given_cell_by_cell_is_type_only():
    schedule = schedule_from_cells("DIFFUSER SCHEDULE", ["TYPE", "CFM"], [["CD", "200"], ["EG", "150"]], [],
                                   (DOC, 1, "H601"))
    assert schedule.type_only and [r.cells["TYPE"] for r in schedule.rows] == ["CD", "EG"]


def test_the_large_pictures_are_found_as_the_sheet_is_viewed(tmp_path):
    with _picture_sheet(tmp_path, boxes=((300, 300, 1300, 800), (2800, 50, 2850, 80)), rotate=90) as pdf:
        page = pdf[0]
        [box] = picture_regions(page)                 # the small logo-sized one is left out
        assert box.width == pytest.approx(500, abs=2) and box.height == pytest.approx(1000, abs=2)   # turned


def test_a_picture_is_drawn_once_into_the_cache_and_a_big_one_is_also_cut_into_tiles(tmp_path):
    with _picture_sheet(tmp_path, boxes=((300, 300, 1100, 700), (100, 1000, 2900, 1200))) as pdf:
        pictures = render_pictures(pdf[0], tmp_path / "images", "abc-p1")
        assert [p.path.name for p in pictures] == ["abc-p1-1.png", "abc-p1-2.png"]
        assert pictures[0].tiles == ()
        small = pymupdf.Pixmap(str(pictures[0].path))
        assert small.width == pytest.approx(800 * 200 / 72, abs=3)           # 200 dpi
        wide = pymupdf.Pixmap(str(pictures[1].path))
        assert wide.width <= 2800 * 100 / 72 + 3 and len(pictures[1].tiles) == 2
        assert all(pymupdf.Pixmap(str(t)).width <= MAX_EDGE for t in pictures[1].tiles)
        stamp = pictures[0].path.stat().st_mtime_ns
        render_pictures(pdf[0], tmp_path / "images", "abc-p1")
        assert pictures[0].path.stat().st_mtime_ns == stamp


def test_a_picture_schedule_sheet_is_read_by_eye_instead_of_counted_from_its_ocr_text(tmp_path):
    judge = FakeJudge()
    flags = []
    with _picture_sheet(tmp_path) as pdf:
        schedules = read_schedules(_catalogue(), lambda d, p: pdf[p - 1], None, flags, judge, tmp_path / "images")
    [image, sheet, page, hint, tiles] = judge.calls[0]
    assert (sheet, page, hint) == ("H601", 1, "EXHAUST FAN SCHEDULE") and image.exists()
    assert image.parent == tmp_path / "images" and image.name.endswith("-p1-1.png")
    [schedule] = schedules
    assert schedule.source == BY_EYE and not schedule.from_text
    assert [r.tag for r in schedule.rows] == ["UH-1", "UH-2", "UH-3", "CUH-1"]
    assert flags == ["H601: 1 schedules read by eye from 1 pictures of the sheet — check the counts"]


def test_with_no_answer_yet_the_ocr_text_count_stays_and_says_so(tmp_path):
    judge = FakeJudge(answer=None)
    flags = []
    with _picture_sheet(tmp_path) as pdf:
        schedules = read_schedules(_catalogue(), lambda d, p: pdf[p - 1], None, flags, judge, tmp_path / "images")
    assert [(s.from_text, [r.tag for r in s.rows]) for s in schedules] == [(True, ["EF-1"])]
    assert flags == ["H601: 1 of its 1 schedule pictures not read by eye yet (judgement pending — waiting for an "
                     "answer in the chat); counted from the sheet's text meanwhile"]


def test_without_a_judge_nothing_is_drawn(tmp_path):
    with _picture_sheet(tmp_path) as pdf:
        schedules = read_schedules(_catalogue(), lambda d, p: pdf[p - 1], None, [])
    assert [s.from_text for s in schedules] == [True]
    assert not (tmp_path / "images").exists()


def test_a_sheet_whose_tables_read_well_is_not_read_by_eye(tmp_path):
    from test_schedules import grid
    from pdfs import Page, make_pdf
    lines, texts = grid(300, 300, [90, 120, 70], [["EXHAUST FAN SCHEDULE", "", ""], ["TAG", "SERVES", "CFM"],
                                                  ["EF-1", "TOILET", "100"], ["EF-2", "TOILET", "100"]])
    path = make_pdf(tmp_path / DOC, Page(W, H, tuple(texts), lines=lines))
    judge = FakeJudge()
    tags = [TagEntry("EF-1", "Exhaust Fan", ("H601",), ("H101",), 2), TagEntry("EF-2", "Exhaust Fan", ("H601",), ("H101",), 2)]
    with pymupdf.open(str(path)) as pdf:
        catalogue = _catalogue(tags=tags)
        catalogue.pages = (PageRecord(DOC, 1, "text", "EXHAUST FAN SCHEDULE TAG SERVES CFM EF-1 EF-2", 0, True),)
        schedules = read_schedules(catalogue, lambda d, p: pdf[p - 1], None, [], judge, tmp_path / "images")
    assert [r.tag for s in schedules for r in s.rows] == ["EF-1", "EF-2"] and judge.calls == []
