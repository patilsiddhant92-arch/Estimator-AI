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
# T-009 (ruling 22): the template's two demolition exclusions. A proposal prints one: the specific line when the job
# has a Demolition Scope block, the general one otherwise.
DEMOLITION_GENERAL = "Any demolition work not mentioned."
DEMOLITION_SPECIFIC = "Any demolition work not specifically mentioned"
DEMOLITION_BLOCK_KEY = "demolition"            # the same strings as bms.render.DEMOLITION_KEY / DEMOLITION_HEADING;
DEMOLITION_BLOCK_HEADING = "Demolition Scope"  # estimator code does not import bms
BASE_PRICE = "Base Price:"
EXISTING_NAME_COLOUR = "FF0000"   # the template types the existing system's name in red
# Ruling 26 (G-005): the sentence the writer prints, in red, as a sub-bullet under the off-hours exclusion ({hours} the
# time range as spoken, {source} where the documents say it). The reader skips a sub-bullet among the exclusions only
# when its text has one of these forms (`read._exclusions`).
OFF_HOURS_BETWEEN = "The documents require work between {hours} ({source})."
OFF_HOURS_UNSTATED = "The documents require off-hours work ({source})."

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
    font: str | None = None           # run font name; None = from the style


BLANK = ParagraphFormat(style="Normal")
# Block headers and the unnumbered group heading are PR2 style, which Word already shows as
# Calibri — font is still set explicitly below so the runs say so themselves, not the style.
BLOCK_HEADER = ParagraphFormat(style=OUTLINE_STYLE, indent=1566, space_after=0, size=12, bold=True, font="Calibri")
# An unnumbered group heading, such as "Kitchen Exhaust System" — measured on the sent 26-0246
# proposal: PR2, bold 12pt like BLOCK_HEADER, but numbering explicitly switched off (list 0) and
# no indent override, so it sits flush with the front-end text rather than a block header's line.
GROUP_HEADING = ParagraphFormat(style=OUTLINE_STYLE, list_id=0, level=0, space_after=0, size=12, bold=True,
                                 font="Calibri")
# Block lines and notes are Normal style, whose own font is Myriad Pro — but the team's sent
# proposals set every equipment-block word to Calibri, so both are forced to Calibri here too.
BLOCK_NOTE = ParagraphFormat(style="Normal", indent=1440, space_after=0, font="Calibri")
FRONT_END_NOTE = ParagraphFormat(style="Normal", indent=720, font="Calibri")
FRONT_END_NOTE_GAP = ParagraphFormat(style="Normal", size=6)


def block_line(depth: int) -> ParagraphFormat:
    """A bulleted line under a block header. Depth 1 is list 12 level 4; depth 5 is level 8."""
    return ParagraphFormat(style="Normal", list_id=BLOCK_LINE_LIST, level=3 + depth, space_after=0, font="Calibri")


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
