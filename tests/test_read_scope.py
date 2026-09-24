from collections import Counter

import docx
import pytest

from conftest import PROPOSAL_TEMPLATE, SENT_PROPOSAL
from estimator.proposal.read import ProposalFormatError, read_proposal
from estimator.text import squash

MISC_MONITORING_DEPTHS = [1, 2, 3, 2, 3, 2, 3, 2, 4, 4, 4, 4, 4, 4, 4, 3, 2, 2, 2, 3, 3, 2, 3, 3, 2, 3, 3, 3, 3, 4, 2]


def test_scope_heading_and_front_end(sent_scope):
    suffix, front_end, *_ = sent_scope
    assert suffix == "PREWAILING WAGE"
    assert (front_end.mode, front_end.existing_system_name) == ("new-system", None)
    assert [item.kind for item in front_end.items] == ["line"] * 7 + ["note"] * 5
    assert front_end.items[0].text == "Furnish Network Level Control Panel"
    assert front_end.items[1].text == "Furnish PC Workstation (School Operator Console )"
    assert front_end.items[5].text == "Furnish 3-D Graphics"
    assert all(run.bold for item in front_end.items for run in item.runs)


def test_blocks(sent_scope):
    blocks = sent_scope[2]
    assert len(blocks) == 44
    assert blocks[0].header == "*Qty (1) BACnet Data Cabinet"
    assert blocks[-1].header == "Provide 2 Year Guarantee for Workmanship and Material – 15970-49"
    items = [item for block in blocks for item in block.items]
    assert len(items) == 204
    assert Counter((i.kind, i.depth) for i in items) == {
        ("line", 1): 137, ("line", 2): 31, ("line", 3): 15, ("line", 4): 8, ("note", 1): 13}


def test_nesting_is_read_from_the_indent(sent_scope):
    misc = next(b for b in sent_scope[2] if b.header == "Misc Monitoring Systems")
    assert [item.depth for item in misc.items] == MISC_MONITORING_DEPTHS
    assert all(item.kind == "line" for item in misc.items)


def test_emphasis_survives(sent_scope):
    cabinet = sent_scope[2][0]
    server = next(i for i in cabinet.items if squash(i.text) == "Furnish and Install (Rack Mounted) BACnet Server")
    assert [run.text.strip() for run in server.runs if run.bold] == ["(Rack Mounted)"]


def test_alternates(sent_scope):
    add, deduct = sent_scope[3], sent_scope[4]
    assert [a.label for a in add] == ["ALT 1: Controls As per Sequence of operation 15985 – 18"]
    assert [b.header for b in add[0].blocks] == ["*Qty (1) Can Wash Kitchen Exhaust Fan EF-9"]
    assert [i.text for i in add[0].blocks[0].items] == [
        "Furnish and Install DDC Controller", "Furnish Fan Start / Stop and Status"]
    assert [a.label for a in deduct] == ["ALT #:"]
    assert [b.header for b in deduct[0].blocks] == ["Qty (1) Shower Room Exhaust Fan EF-2"]
    assert [i.kind for i in deduct[0].blocks[0].items] == ["line", "line", "note"]


def test_the_whole_proposal(sent_job):
    assert sent_job.header.quote_number == "26-0246"
    assert sent_job.scope_heading_suffix == "PREWAILING WAGE"
    assert len(sent_job.blocks) == 44
    assert sent_job.named_exceptions == ("EXCEPTION TO ANY WORK WITH EXHAUST FAN EF-4 (24/7 OPERATION)",)
    assert sent_job.front_end.tech_hours is None and sent_job.blocks[0].items[0].quantity is None


def test_a_table_inside_the_scope_is_refused(tmp_path):
    document = docx.Document(str(SENT_PROPOSAL))
    table = document.add_table(rows=1, cols=1)
    heading = next(p for p in document.paragraphs if squash(p.text).startswith("SCOPE OF WORK"))
    heading._p.addnext(table._tbl)
    edited = tmp_path / "with-table.docx"
    document.save(str(edited))
    with pytest.raises(ProposalFormatError, match="table"):
        read_proposal(edited, PROPOSAL_TEMPLATE)
