"""The layout of an AME proposal: its fixed headings, and how each kind of line looks.

Every format here uses a list the AME template already defines — measured on the
template and on the proposal sent for 26-0246. Each kind of line has exactly one
format, so a proposal never ends up with the same kind of line in two fonts or
two different bullets.
"""
from __future__ import annotations

from dataclasses import dataclass

from estimator.scope import FrontEnd, Job

# Fixed wording the tool looks for in the template.
OPENING = "A.M.E., Inc, is pleased to provide a quotation"
SCOPE_HEADING = "SCOPE OF WORK –"
NEW_SYSTEM_HEADING = "Front End Web Enabled BMS System"
EXISTING_SYSTEM_HEADING = "Seamlessly Tie in to the Existing"
OR_LINE = "OR"
ADD_ALTERNATES = "ADD ALTERNATES:"
DEDUCT_ALTERNATES = "DEDUCT ALTERNATES:"
ALTERNATE_LABEL = "ALT #:"
CLARIFICATIONS = "Clarifications and Inclusions considered:"
EXCLUSIONS = "Exceptions and Exclusions"
BASE_PRICE = "Base Price:"
EXISTING_NAME_COLOUR = "FF0000"   # the template types the existing system's name in red

# The lists the template defines.
BLOCK_LINE_LIST = 12              # o ➢ ▪ • at levels 4-8; indents 1800, 2160, 2520, 2880, 3240
FRONT_END_LIST = {"new-system": 11, "extend-existing": 10}
OUTLINE_STYLE = "PR2"             # numbered 1., 2., 3. by the template's outline list

# Where Word starts depth-1 text, and how far each deeper level steps in (twips).
BLOCK_LINE_INDENT, BLOCK_LINE_STEP = 1800, 360
FRONT_END_LINE_INDENT, FRONT_END_LINE_STEP = 1440, 720


@dataclass(frozen=True)
class ParagraphFormat:
    style: str                        # Word style name
    list_id: int | None = None        # bullet list; None = no bullet
    level: int | None = None
    indent: int | None = None         # left indent in twips; None = from the list or style
    space_after: int | None = None    # points
    size: float | None = None         # font size in points; None = from the style
    bold: bool | None = None          # True forces bold; None = each run's own emphasis


BLANK = ParagraphFormat(style="Normal")
BLOCK_HEADER = ParagraphFormat(style=OUTLINE_STYLE, indent=1566, space_after=0, size=12, bold=True)
BLOCK_NOTE = ParagraphFormat(style="Normal", indent=1440, space_after=0)
FRONT_END_NOTE = ParagraphFormat(style="Normal", indent=720)


def block_line(depth: int) -> ParagraphFormat:
    """A bulleted line under a block header. Depth 1 is list 12 level 4; depth 5 is level 8."""
    return ParagraphFormat(style="Normal", list_id=BLOCK_LINE_LIST, level=3 + depth, space_after=0)


def front_end_line(mode: str, depth: int) -> ParagraphFormat:
    return ParagraphFormat(style="Normal", list_id=FRONT_END_LIST[mode], level=depth, size=12)


# What Word draws in front of each kind of line — written into the price sheet as text.
BLOCK_LINE_MARKER = {1: "o", 2: "➢", 3: "▪", 4: "•", 5: "◦"}
FRONT_END_LINE_MARKER = {"new-system": {1: "o", 2: "▪"}, "extend-existing": {1: "•", 2: "o"}}
FRONT_END_HEADING_MARKER = "•"


def scope_heading(job: Job) -> str:
    return f"{SCOPE_HEADING} {job.scope_heading_suffix}".strip()


def front_end_heading(front_end: FrontEnd) -> str:
    if front_end.mode == "new-system":
        return NEW_SYSTEM_HEADING
    return f"{EXISTING_SYSTEM_HEADING} {front_end.existing_system_name} BMS"
