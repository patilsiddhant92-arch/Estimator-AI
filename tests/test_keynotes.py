from types import SimpleNamespace

from estimator.catalogue.register import PageRecord
from estimator.catalogue.sheet_types import Sheet
from estimator.reading.keynotes import read_notes

DOC = "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"


def _page(text: str, page: int = 1, document: str = DOC) -> PageRecord:
    return PageRecord(document, page, "text", text, 0)


def _sheet(number: str, page: int = 1, document: str = DOC) -> Sheet:
    return Sheet(document, page, number, "MECHANICAL PLAN", "Mechanical", ())


def _catalogue(pages, sheets):
    return SimpleNamespace(pages=pages, sheets=sheets)


def test_a_key_note_that_names_controls_scope_is_flagged_and_one_that_doesnt_isnt():
    text = (
        "KEY NOTES:\n"
        "1. PROVIDE SPACE STATIC PRESSURE SENSOR. BY CONTROLS CONTRACTOR.\n"
        "2. DUCT DOWN TO UNIT.\n"
    )
    page = _page(text)
    sheet = _sheet("M-201")
    notes = read_notes(_catalogue([page], [sheet]))
    assert len(notes) == 2
    one, two = notes
    assert one.block == "KEY NOTES" and one.number == "1"
    assert one.controls is True
    assert one.text == "PROVIDE SPACE STATIC PRESSURE SENSOR. BY CONTROLS CONTRACTOR."
    assert one.sheet == "M-201" and one.document == DOC and one.page == 1
    assert two.number == "2" and two.controls is False


def test_lettered_general_notes_are_split_and_read():
    text = (
        "GENERAL NOTES:\n"
        "A. PROVIDE CONDUIT FOR BAS WIRING.\n"
        "B. INSULATE ALL PIPING PER SPEC.\n"
    )
    page = _page(text)
    sheet = _sheet("M-001")
    notes = read_notes(_catalogue([page], [sheet]))
    assert [n.number for n in notes] == ["A", "B"]
    assert notes[0].block == "GENERAL NOTES"
    assert notes[0].controls is True    # BAS
    assert notes[1].controls is False


def test_a_by_others_note_names_who_and_counts_as_controls():
    text = (
        "KEY NOTES:\n"
        "7. FIRE/SMOKE DAMPER INTERLOCK WIRING BY OTHERS.\n"
    )
    page = _page(text)
    sheet = _sheet("M-202")
    notes = read_notes(_catalogue([page], [sheet]))
    assert len(notes) == 1
    assert notes[0].who == "by others"
    assert notes[0].controls is True


def test_placements_are_never_counted_just_the_list():
    text = (
        "KEY NOTES:\n"
        "1. PROVIDE THERMOSTAT AT 48 IN AFF.\n"
    )
    page = _page(text)
    sheet = _sheet("M-203")
    notes = read_notes(_catalogue([page], [sheet]))
    assert len(notes) == 1
    # No count field at all is exposed on Note — the module never tallies placements.
    assert not hasattr(notes[0], "count")


def test_a_numbered_list_on_a_spec_page_is_not_read_drawing_sheets_only():
    text = (
        "SECTION 23 09 93 SEQUENCE OF OPERATIONS\n"
        "1. THE BAS SHALL MONITOR SPACE TEMPERATURE.\n"
        "2. THE UNIT SHALL BE ENABLED BY SCHEDULE.\n"
    )
    page = _page(text, document="2. Takeoffs/1. Base Takeoff/Specs.pdf")
    notes = read_notes(_catalogue([page], []))    # no Sheet for this page — it's a spec page
    assert notes == []


def test_a_block_ends_at_the_next_heading():
    text = (
        "KEY NOTES:\n"
        "1. PROVIDE A DAMPER ACTUATOR.\n"
        "GENERAL NOTES:\n"
        "1. COORDINATE WITH ELECTRICAL.\n"
    )
    page = _page(text)
    sheet = _sheet("M-204")
    notes = read_notes(_catalogue([page], [sheet]))
    assert [n.block for n in notes] == ["KEY NOTES", "GENERAL NOTES"]
    assert notes[0].text == "PROVIDE A DAMPER ACTUATOR."
    assert notes[1].text == "COORDINATE WITH ELECTRICAL."


def test_no_heading_on_the_page_gives_no_notes():
    page = _page("JUST SOME MECHANICAL PLAN TEXT WITH NO NOTE BLOCK AT ALL ON IT.")
    sheet = _sheet("M-205")
    notes = read_notes(_catalogue([page], [sheet]))
    assert notes == []


# ---- where the last note of a block ends (review finding 4) ------------------------------------

def test_a_note_ends_at_a_blank_line():
    text = "KEY NOTES:\n1. PROVIDE A DAMPER ACTUATOR\nON THE OUTSIDE AIR DAMPER.\n\nROOM 101\nCORRIDOR\n"
    [note] = read_notes(_catalogue([_page(text)], [_sheet("M-201")]))
    assert note.text == "PROVIDE A DAMPER ACTUATOR ON THE OUTSIDE AIR DAMPER."


def test_a_note_ends_at_any_heading():
    text = "KEY NOTES:\n1. PROVIDE A DAMPER ACTUATOR.\nDEMOLITION LEGEND:\nEXISTING TO BE REMOVED\n"
    [note] = read_notes(_catalogue([_page(text)], [_sheet("M-201")]))
    assert note.text == "PROVIDE A DAMPER ACTUATOR."


def test_a_note_ends_where_the_title_block_starts():
    from estimator.catalogue.pdf import Span

    text = ("KEY NOTES:\n1. PROVIDE A DAMPER ACTUATOR.\nACME ENGINEERING GROUP\n123 MAIN STREET\n"
            "SECOND FLOOR PLAN\n")
    strip = tuple(Span(t, 10, 0.85, 0.85 + i * 0.02, 0.95, 0.86 + i * 0.02)
                  for i, t in enumerate(("ACME ENGINEERING GROUP", "123 MAIN STREET", "SECOND FLOOR PLAN")))
    page = PageRecord(DOC, 1, "text", text, 0, True, strip)
    [note] = read_notes(_catalogue([page], [_sheet("M-201")]))
    assert note.text == "PROVIDE A DAMPER ACTUATOR."


def test_a_notes_block_set_in_the_title_block_strip_is_still_read():
    from estimator.catalogue.pdf import Span

    text = "KEY NOTES:\n1. PROVIDE A DAMPER ACTUATOR\nON THE OUTSIDE AIR DAMPER.\n"
    strip = tuple(Span(t, 10, 0.85, 0.3 + i * 0.02, 0.95, 0.31 + i * 0.02)
                  for i, t in enumerate(("KEY NOTES:", "1. PROVIDE A DAMPER ACTUATOR", "ON THE OUTSIDE AIR DAMPER.")))
    page = PageRecord(DOC, 1, "text", text, 0, True, strip)
    [note] = read_notes(_catalogue([page], [_sheet("M-201")]))
    assert note.text == "PROVIDE A DAMPER ACTUATOR ON THE OUTSIDE AIR DAMPER."


def test_a_note_longer_than_600_characters_is_cut_and_says_so():
    long = " ".join(["PROVIDE CONTROL WIRING TO EACH DAMPER ACTUATOR"] * 30)
    [note] = read_notes(_catalogue([_page(f"KEY NOTES:\n1. {long}\n")], [_sheet("M-201")]))
    assert note.text.endswith(" …") and len(note.text) <= 602
    assert note.text.startswith("PROVIDE CONTROL WIRING")


def test_the_sixtieth_note_ends_where_the_sixty_first_starts():
    lines = "".join(f"{n}. NOTE NUMBER {n}.\n" for n in range(1, 71))
    notes = read_notes(_catalogue([_page(f"KEY NOTES:\n{lines}")], [_sheet("M-201")]))
    assert len(notes) == 60
    assert notes[-1].number == "60" and notes[-1].text == "NOTE NUMBER 60."


def test_only_the_pages_given_are_read():
    text = "KEY NOTES:\n1. PROVIDE A DAMPER ACTUATOR.\n"
    pages = [_page(text, page=1), _page(text, page=2)]
    notes = read_notes(_catalogue(pages, [_sheet("M-201", page=1), _sheet("M-201", page=2)]), pages={(DOC, 2)})
    assert [n.page for n in notes] == [2]


def test_a_note_whose_number_stands_alone_on_its_line_is_still_read():
    from estimator.catalogue.pdf import Span

    text = "KEY NOTES:\n1. \nPROVIDE A RETURN AIR SENSOR\nWIRED TO THE BMS.\n"
    strip = tuple(Span(t, 10, 0.85, 0.3 + i * 0.02, 0.95, 0.31 + i * 0.02)
                  for i, t in enumerate(("PROVIDE A RETURN AIR SENSOR", "WIRED TO THE BMS.")))
    page = PageRecord(DOC, 1, "text", text, 0, True, strip)
    [note] = read_notes(_catalogue([page], [_sheet("M-201")]))
    assert note.text == "PROVIDE A RETURN AIR SENSOR WIRED TO THE BMS." and note.controls
