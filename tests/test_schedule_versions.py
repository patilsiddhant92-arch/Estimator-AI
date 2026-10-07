"""RD-1: a schedule sheet read from two documents is never dropped by its number alone.

The schedules come from the governing pages (`governing_pages`), which keep both documents' pages whenever nothing
proves one replaces the other ("When nothing says which one wins, both are counted"; "The other page is kept and
counted"). Only a page of a proven marked-up copy (`repeats`) is set aside. Invented fixtures only (job 26-9999,
invented sheets and tags); no job is run."""
from __future__ import annotations

from estimator.catalogue.job import catalogue_job
from estimator.reading.job import read_job
from pdfs import FILLER, Page, make_pdf
from test_schedules import grid

W, H = 3024, 2160
HEADERS = ["TAG", "SERVES", "MAX CFM", "MANUFACTURER"]


def _schedule_sheet(title: str, tags: list[str], sheet_title: str = "HVAC SCHEDULES") -> Page:
    rows = [[title, "", "", ""], HEADERS] + [[tag, f"ROOM {n}", "600", "ACME"] for n, tag in enumerate(tags, 101)]
    lines, texts = grid(300, 300, [90, 120, 70, 100], rows)
    return Page(W, H, ((200, 200, FILLER, 12), *texts, (2640, 1860, sheet_title, 20), (2800, 2000, "M-601", 40)),
                lines=lines)


def _plan(tags: list[str]) -> Page:
    labels = tuple((900 + 150 * n, 900, tag, 12) for n, tag in enumerate(tags))
    return Page(W, H, ((200, 300, FILLER, 12), *labels, (2640, 1860, "FIRST FLOOR PLAN", 20),
                       (2800, 2000, "M-101", 40)))


def _scheduled(reading) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for item in reading.inventory:
        if item.schedule:
            found.setdefault(item.tag.split("-")[0], set()).add(item.tag)
    return found


def test_an_addendum_reissuing_one_page_of_a_two_page_schedule_sheet_keeps_both_schedules(tmp_path):
    """Base M-601 p.1 is the VAV schedule, p.2 the fan schedule; the addendum reissues p.1 alone, adding VAV-4. The
    addendum's p.1 governs, base p.2 is kept: both schedules are read, VAV-4 included."""
    root = tmp_path / "26-9999, 1 Test Street"
    vavs = ["VAV-1", "VAV-2", "VAV-3"]
    make_pdf(root / "2. Takeoffs" / "1. Base Takeoff" / "Mech.pdf",
             _schedule_sheet("VAV BOX SCHEDULE", vavs), _schedule_sheet("EXHAUST FAN SCHEDULE", ["EF-1", "EF-2"]),
             _plan(vavs + ["EF-1", "EF-2"]))
    make_pdf(root / "2. Takeoffs" / "2. Addendum 1" / "Addendum 1 Mech.pdf",
             _schedule_sheet("VAV BOX SCHEDULE", vavs + ["VAV-4"]))
    reading = read_job(catalogue_job(root, tmp_path / "cache"))
    [s] = reading.supersessions
    assert s.current.document.endswith("Addendum 1 Mech.pdf")
    assert [(v.document.rsplit("/", 1)[-1], v.page) for v in s.replaced] == [("Mech.pdf", 1)]
    assert any("unmatched page kept (p.2)" in f for f in reading.flags)
    scheduled = _scheduled(reading)
    assert scheduled.get("VAV") == {"VAV-1", "VAV-2", "VAV-3", "VAV-4"}
    assert scheduled.get("EF") == {"EF-1", "EF-2"}
    totals = dict((t.prefix, t.scheduled) for t in reading.totals)
    assert totals.get("VAV") == 4 and totals.get("EF") == 2


def test_two_undated_documents_each_with_its_own_schedule_sheet_are_both_read(tmp_path):
    """Two base documents, no dates to order them, each with its own M-601 listing other units: both are read and
    summed ("summed, for now"), never the first document's alone."""
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet("VAV BOX SCHEDULE", ["VAV-1", "VAV-2"]), _plan(["VAV-1", "VAV-2"]))
    make_pdf(base / "Mech reissue.pdf", _schedule_sheet("VAV BOX SCHEDULE", ["VAV-11", "VAV-12", "VAV-13"]))
    reading = read_job(catalogue_job(root, tmp_path / "cache"))
    assert _scheduled(reading).get("VAV") == {"VAV-1", "VAV-2", "VAV-11", "VAV-12", "VAV-13"}
    assert dict((t.prefix, t.scheduled) for t in reading.totals).get("VAV") == 5


def test_a_tag_both_undated_documents_list_is_counted_once_and_names_both_documents(tmp_path):
    """The two versions share VAV-2: it is one unit (the higher of 1 and 1), never two, and its note names both
    documents; the tags only one version lists are summed beside it."""
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet("VAV BOX SCHEDULE", ["VAV-1", "VAV-2"]), _plan(["VAV-1", "VAV-2"]))
    make_pdf(base / "Mech reissue.pdf", _schedule_sheet("VAV BOX SCHEDULE", ["VAV-2", "VAV-3"]))
    reading = read_job(catalogue_job(root, tmp_path / "cache"))
    items = {i.tag: i for i in reading.inventory}
    assert _scheduled(reading).get("VAV") == {"VAV-1", "VAV-2", "VAV-3"}
    assert dict((t.prefix, t.scheduled) for t in reading.totals).get("VAV") == 3
    shared = items["VAV-2"]
    assert (shared.category, shared.quantity) == ("DISCREPANCY", 1)
    assert "M-601 in Mech.pdf" in shared.reason and "M-601 in Mech reissue.pdf" in shared.reason


def test_two_versions_giving_a_type_other_quantities_count_the_higher_and_say_both():
    from estimator.reading.inventory import build_inventory
    from estimator.reading.schedules import Schedule, ScheduleRow
    from test_inventory import catalogue_with

    def listing(document, quantity):
        row = ScheduleRow("HP-A", {"TAG": "HP-A", "QUANTITY": quantity}, None, None, False)
        return Schedule(document, 1, "M-601", "HEAT PUMP SCHEDULE", ("TAG", "QUANTITY"), (row,), False, (), ())

    items, totals, _ = build_inventory(catalogue_with([]), [listing("Mech.pdf", "3"), listing("Mech reissue.pdf", "5")])
    [item] = [i for i in items if i.tag == "HP-A"]
    assert item.quantity == 5
    assert "3 in Mech.pdf" in item.reason and "5 in Mech reissue.pdf" in item.reason and item.action == "confirm"
    assert dict((t.prefix, t.scheduled) for t in totals).get("HP") == 5


def test_only_a_proven_marked_up_copy_of_the_set_is_set_aside_and_its_note_gives_both_numbers():
    """Two documents with the same sheets, tags and text: `repeats` proves one a marked-up copy. Its M-601 is read
    from the original alone, and the note says how many rows were set aside and how many were counted."""
    from estimator.catalogue.job import repeats
    from estimator.reading.inventory import build_inventory
    from test_dossier_plan_areas import DWG, OTHER, _schedule
    from test_review_final6_counts import _two_buildings

    catalogue, a, _b = _two_buildings(same_tags=True)
    copies = repeats(catalogue)[1]
    copy = next(document for number, document in copies if number == "M-601")
    original = OTHER if copy == DWG else DWG
    tags = [t for f in a for t in f]
    items, totals, flags = build_inventory(catalogue, [_schedule("VAV SCHEDULE", tags, 4, document=original),
                                                       _schedule("VAV SCHEDULE", tags, 4, document=copy)])
    assert dict((t.prefix, t.scheduled) for t in totals).get("VAV") == 9
    assert not [i for i in items if i.category == "DISCREPANCY"]
    name = lambda d: d.rsplit("/", 1)[-1]
    assert (f"1 schedule on M-601 in {name(copy)} not counted (9 tagged rows) — a marked-up copy of the set; "
            f"M-601 counted from {name(original)} (9 tagged rows)") in flags


def _type_only(document, *codes_and_quantities):
    from estimator.reading.schedules import Schedule, ScheduleRow
    rows = tuple(ScheduleRow(None, {"UNIT NO.": code, "QUANTITY": quantity}, None, None, False)
                 for code, quantity in codes_and_quantities)
    return Schedule(document, 1, "M-602", "HEAT PUMP AIR CONDITIONING UNIT SCHEDULE", ("UNIT NO.", "QUANTITY"), rows,
                    True, (), ())


def test_a_type_code_only_the_second_version_of_a_type_only_schedule_adds_is_counted():
    from estimator.reading.inventory import build_inventory
    from test_inventory import catalogue_with

    items, totals, _ = build_inventory(catalogue_with([]), [_type_only("Mech.pdf", ("HPAC", "40")),
                                                            _type_only("Mech reissue.pdf", ("HPAC", "40"),
                                                                       ("HPBC", "12"))])
    got = {i.tag: i for i in items}
    assert (got["HPAC"].category, got["HPAC"].quantity) == ("CONFIRMED", 40)
    assert (got["HPBC"].category, got["HPBC"].quantity) == ("CONFIRMED", 12)
    assert not [i for i in items if i.category == "TYPE ONLY"]
    assert dict((t.prefix, t.scheduled) for t in totals) == {"HPAC": 40, "HPBC": 12}


def test_two_versions_of_a_type_only_schedule_giving_other_quantities_count_the_higher_and_say_both():
    from estimator.reading.inventory import build_inventory
    from test_inventory import catalogue_with

    items, totals, _ = build_inventory(catalogue_with([]), [_type_only("Mech.pdf", ("HPAC", "40")),
                                                            _type_only("Mech reissue.pdf", ("HPAC", "44"))])
    [item] = [i for i in items if i.tag == "HPAC"]
    assert item.quantity == 44 and item.action == "confirm"
    assert "40 in Mech.pdf" in item.reason and "44 in Mech reissue.pdf" in item.reason
    assert not [i for i in items if i.category == "TYPE ONLY"]
    assert dict((t.prefix, t.scheduled) for t in totals) == {"HPAC": 44}
