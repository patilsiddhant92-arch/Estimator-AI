import datetime as dt

import pytest
from pydantic import ValidationError

from estimator.scope import Block, FrontEnd, Header, Item, Job, Run


def test_item_text_joins_its_runs():
    item = Item(kind="line", runs=(Run(text="Furnish and Install "), Run(text="(Rack Mounted)", bold=True), Run(text=" BACnet Server")))
    assert item.text == "Furnish and Install (Rack Mounted) BACnet Server"


def test_an_item_needs_text():
    with pytest.raises(ValidationError, match="needs some text"):
        Item(kind="line", runs=(Run(text="   "),))


def test_a_note_is_never_nested():
    with pytest.raises(ValidationError, match="depth 1"):
        Item(kind="note", depth=2, runs=(Run(text="*BY OTHERS"),))


def test_a_note_has_no_quantity():
    with pytest.raises(ValidationError, match="no quantity"):
        Item(kind="note", runs=(Run(text="*BY OTHERS"),), quantity=2)


def test_depth_is_one_to_five():
    with pytest.raises(ValidationError):
        Item(kind="line", depth=6, runs=(Run(text="x"),))


def test_extending_an_existing_bms_needs_its_name():
    with pytest.raises(ValidationError, match="existing system's name"):
        FrontEnd(mode="extend-existing")


def test_a_new_system_has_no_existing_name():
    with pytest.raises(ValidationError, match="no existing system name"):
        FrontEnd(mode="new-system", existing_system_name="Honeywell")


def test_front_end_lines_are_at_most_two_deep():
    with pytest.raises(ValidationError, match="two levels"):
        FrontEnd(mode="new-system", items=(Item(kind="line", depth=3, runs=(Run(text="x"),)),))


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        Block(header="Qty (1) EF-1", colour="red")


def test_the_cover_needs_a_drawing_list():
    with pytest.raises(ValidationError):
        Header(date=dt.date(2026, 1, 1), quote_number="26-1", reference="r", mep_engineer="m", based_on=())


def test_a_job_survives_a_trip_through_json(small_job):
    assert Job.model_validate_json(small_job.model_dump_json()) == small_job


def test_without_prices_clears_hours_and_quantities(small_job, without_prices):
    bare = without_prices(small_job)
    assert bare.front_end.tech_hours is None
    assert all(b.tech_hours is None for b in bare.blocks)
    assert all(i.quantity is None for b in bare.blocks for i in b.items)
    assert bare.blocks[0].header == small_job.blocks[0].header
