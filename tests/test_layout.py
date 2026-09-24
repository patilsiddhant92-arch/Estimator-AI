import pytest

from estimator.proposal import layout
from estimator.proposal.word import WordLists
from estimator.scope import FrontEnd
from estimator.text import squash


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_every_block_line_depth_is_a_level_the_template_defines(template_document, depth):
    lists = WordLists(template_document)
    fmt = layout.block_line(depth)
    assert lists.has_level(fmt.list_id, fmt.level)
    assert lists.level_indent(fmt.list_id, fmt.level) == layout.BLOCK_LINE_INDENT + layout.BLOCK_LINE_STEP * (depth - 1)


@pytest.mark.parametrize("mode", ["new-system", "extend-existing"])
@pytest.mark.parametrize("depth", [1, 2])
def test_every_front_end_depth_is_a_level_the_template_defines(template_document, mode, depth):
    lists = WordLists(template_document)
    fmt = layout.front_end_line(mode, depth)
    assert lists.level_indent(fmt.list_id, fmt.level) == layout.FRONT_END_LINE_INDENT + layout.FRONT_END_LINE_STEP * (depth - 1)


def test_block_headers_are_numbered_by_their_style(template_document):
    assert layout.BLOCK_HEADER.style == layout.OUTLINE_STYLE and layout.BLOCK_HEADER.list_id is None
    assert WordLists(template_document).style_numbering(layout.OUTLINE_STYLE) is not None


def test_scope_lines_are_plain_normal_paragraphs_with_a_bullet():
    # Normal, not PR2: if an estimator later removes the bullet in Word, the line
    # stays a line instead of turning into a numbered block header.
    assert layout.block_line(1).style == "Normal"


def test_every_heading_the_tool_looks_for_is_in_the_template(template_document):
    texts = [squash(p.text) for p in template_document.paragraphs]
    for heading in (layout.OPENING, layout.SCOPE_HEADING, layout.NEW_SYSTEM_HEADING, layout.EXISTING_SYSTEM_HEADING,
                    layout.ADD_ALTERNATES, layout.DEDUCT_ALTERNATES, layout.CLARIFICATIONS, layout.EXCLUSIONS,
                    layout.BASE_PRICE):
        assert any(t.startswith(heading) for t in texts), heading
    assert layout.OR_LINE in texts and texts.count(layout.ALTERNATE_LABEL) == 2


def test_scope_heading(small_job, bare_job):
    assert layout.scope_heading(small_job) == "SCOPE OF WORK – PREVAILING WAGE"
    assert layout.scope_heading(bare_job.model_copy(update={"scope_heading_suffix": ""})) == "SCOPE OF WORK –"


def test_front_end_heading():
    assert layout.front_end_heading(FrontEnd(mode="new-system")) == "Front End Web Enabled BMS System"
    existing = FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs")
    assert layout.front_end_heading(existing) == "Seamlessly Tie in to the Existing Honeywell WEBs BMS"
