"""The scoreboard: the tool's draft proposal against the one the estimator sent.

    estimator score DRAFT_PROPOSAL.docx SENT_PROPOSAL.docx --out FOLDER

It reads both proposals on this machine and writes only FOLDER/<job> Score.xlsx and a summary line: nothing it reads
is copied anywhere else. It is a first measure, not a judge: it matches on words, so it will miscount some wording.

- Systems: each block of the sent proposal matched to the draft's by its tags (normalised, and by type when the
  exact tag differs) and its kind words (abbreviations expanded both ways): matched, quantity differs, missing
  (sent, not in the draft) or extra (in the draft, not sent). A draft block printed as several stacked headers
  ("Qty (a) X / Qty (b) Y") is split into one part per header first, so each can match a different sent block.
- Lines: within matched blocks, each sent line matched to a draft line by its house verb and device words
  (quantities, brackets and punctuation taken off; a token overlap of at least 0.6): matched, worded differently,
  missing or extra.
- Counts: the quantity of each matched block and each matched line that states one: equal or differ.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from estimator.files import open_docx
from estimator.proposal.read import ProposalFormatError, read_blocks_fallback, read_scope
from estimator.text import squash

LINE_OVERLAP = 0.6
MIN_SYSTEM_SCORE = 0.3      # below this, two blocks are treated as unrelated and never paired
QUANTITY_BONUS = 0.25       # equal block/line quantities
QUANTITY_PENALTY = 0.5      # quantities more than 50% apart
MATCHED, DIFFERS, MISSING, EXTRA, WORDED = "matched", "quantity differs", "missing", "extra", "worded differently"
EQUAL, COUNT_DIFFERS = "equal", "differ"
CAVEAT = ("A first measure, not a judge: systems are matched by their tags and kind words, lines by their verb and "
          "device words, so it will miscount some wording. Read the rows before trusting the numbers.")
_VERBS = ("furnish and install", "furnish and wire", "install and wire", "furnish", "install", "wire")
_STOP = frozenset("the a an of for to with at in on and each new per via by from between its all as is are be "
                  "qty total x unit units".split())
_KIND_STOP = _STOP | frozenset("thru through system systems".split())
_HEADER_QTY = re.compile(r"^\*?\s*(?:\(\s*x\s*(\d+)\s*\)|Qty\s*\(\s*([\d#?]+)\s*\))\s*", re.I)
_LINE_QTY = re.compile(r"\(\s*Qty\.?\s*(\d+)\s*(?:Total)?\s*\)|\(\s*x\s*(\d+)\s*\)|\bQty\.?\s*\(\s*(\d+)\s*\)", re.I)
_BRACKETS = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_JOB = re.compile(r"\b\d{2}-\d{4}\b")
ASSETS = Path(__file__).resolve().parents[2] / "assets"
ABBREVIATIONS_FILE = ASSETS / "score_abbreviations.json"


def _load_abbreviations() -> dict[str, str]:
    """House abbreviation (upper-cased) -> the words it stands for (assets/score_abbreviations.json)."""
    data = json.loads(ABBREVIATIONS_FILE.read_text(encoding="utf-8"))
    return {k.upper(): v for k, v in data.items() if k.lower() != "about"}


ABBREVIATIONS = _load_abbreviations()


@dataclass
class ScoreBlock:
    headers: list[str]
    quantity: int | None
    lines: list[tuple[str, int]] = field(default_factory=list)      # (text, depth)
    tags: frozenset = frozenset()        # normalised tags ("-", "_", spaces and "#" dropped)
    stems: frozenset = frozenset()       # each tag's type (its letters before the trailing number)
    kind: frozenset = frozenset()

    @property
    def header(self) -> str:
        return " / ".join(self.headers)


# --- reading a proposal -------------------------------------------------------------------------------------------

def _header_quantity(header: str) -> int | None:
    total, found = 0, False
    for piece in header.split(" / "):
        m = _HEADER_QTY.match(piece.strip())
        if m and (m.group(1) or (m.group(2) or "").isdigit()):
            total += int(m.group(1) or m.group(2))
            found = True
    return total if found else None


_WORDLIKE = re.compile(r"[A-Za-z0-9#][A-Za-z0-9#_-]*")
_PURE_NUM = re.compile(r"^[0-9#]+$")
_LETTERS_THEN_NUM = re.compile(r"^([A-Za-z]+)[0-9#]*$")
_PURE_LETTERS = re.compile(r"^[A-Za-z]+$")


def normalize_tag(text: str) -> str:
    """A tag as it is compared: capitals, with "-", "_", spaces and "#" dropped."""
    return re.sub(r"[-_ #]", "", text.upper())


def tag_stem(tag: str) -> str | None:
    """A tag's type: its last letters group before the trailing number, with any site/floor prefix
    dropped ("HEL05_01_CRAH01" -> "CRAH", "RTU-CR-1" and "RTU-CR1" -> "RTUCR", "DOAU##" -> "DOAU").
    A placeholder ("CRAH-#") gives only this. None when the tag carries no letters to read from."""
    segments = [s for s in re.split(r"[-_]", tag.upper()) if s]
    i = len(segments) - 1
    while i >= 0 and _PURE_NUM.fullmatch(segments[i]):
        i -= 1
    if i < 0:
        return None
    anchor = _LETTERS_THEN_NUM.fullmatch(segments[i])
    if not anchor:
        return None
    tail = anchor.group(1)
    i -= 1
    qualifiers = []
    while i >= 0 and _PURE_LETTERS.fullmatch(segments[i]):
        qualifiers.append(segments[i])
        i -= 1
    return "".join(reversed(qualifiers)) + tail


def _looks_like_tag(token: str) -> bool:
    return bool(re.search(r"[A-Za-z]", token)) and bool(re.search(r"[0-9#]", token)) and tag_stem(token) is not None


def _raw_tags(header: str) -> list[str]:
    """The tag-like tokens a header names, upper-cased, in the order they appear: the dash-joined tags
    the phrasing bank already expands ("EF-1, 2" -> "EF-1", "EF-2"), plus whatever that misses — an
    underscore-joined tag ("HEL05_01_CRAH01") or a placeholder ("CRAH-#", "DOAU##")."""
    from estimator.writing.assemble import header_tags
    out = []
    for piece in header.split(" / "):
        rest = _HEADER_QTY.sub("", piece.strip())
        out += [t.upper() for t in header_tags(rest)]
        out += [t.upper() for t in _WORDLIKE.findall(rest) if _looks_like_tag(t)]
    return list(dict.fromkeys(out))


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _kind_words(header: str, tags: frozenset) -> frozenset:
    words = set()
    for piece in header.split(" / "):
        rest = _HEADER_QTY.sub("", piece.strip())
        for token in re.split(r"[\s,/&()|:;]+", rest):
            token = token.strip("-–.*")
            if not token or re.search(r"\d|#", token) or normalize_tag(token) in tags:
                continue
            expansion = ABBREVIATIONS.get(token.upper())
            pieces = expansion.split() if expansion else re.split(r"[-–]+", token)
            for piece_word in pieces:
                word = _singular(piece_word.casefold())
                if len(word) >= 2 and word not in _KIND_STOP and re.search(r"[a-z]", word):
                    words.add(word)
    return frozenset(words)


def _block(headers: list[str], lines: list[tuple[str, int]]) -> ScoreBlock:
    header = " / ".join(headers)
    raw = _raw_tags(header)
    tags = frozenset(normalize_tag(t) for t in raw)
    stems = frozenset(stem for t in raw if (stem := tag_stem(t)) is not None)
    return ScoreBlock(headers, _header_quantity(header), lines, tags, stems, _kind_words(header, tags))


def read_blocks(path: Path) -> list[ScoreBlock]:
    """The proposal's blocks (base bid and alternates), stacked headers joined over the lines they share. A proposal
    on the AME template is read with `read_scope`; one in the older "(xN)" style by the same fallback the phrasing
    bank uses."""
    document = open_docx(path)
    try:
        _, _, blocks, add, deduct = read_scope(document)
        every = list(blocks) + [b for alternate in (*add, *deduct) for b in alternate.blocks]
    except ProposalFormatError:
        every = []
    if not every:
        return [_block([b["header"]], list(b["lines"])) for b in read_blocks_fallback(document)]
    out, waiting = [], []
    for block in every:
        lines = [(squash(item.text), item.depth) for item in block.items if item.kind == "line"]
        if not block.items:
            waiting.append(block.header)                 # a stacked header: its lines come under the next one
            continue
        out.append(_block(waiting + [block.header], lines))
        waiting = []
    if waiting:
        out.append(_block(waiting, []))
    return out


# --- matching ---------------------------------------------------------------------------------------------------

def _share(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _quantity_adjustment(sent_qty: int | None, draft_qty: int | None) -> float:
    if sent_qty is None or draft_qty is None or not sent_qty:
        return 0.0
    if sent_qty == draft_qty:
        return QUANTITY_BONUS
    if abs(draft_qty - sent_qty) / sent_qty > 0.5:
        return -QUANTITY_PENALTY
    return 0.0


def _system_score(sent: ScoreBlock, draft: ScoreBlock) -> float:
    """How well two blocks match: tag-stem overlap, kind-word overlap (after abbreviation expansion) and
    quantity agreement; 0 when they share neither a tag/stem nor a kind word at all."""
    tags = max(_share(sent.tags, draft.tags), _share(sent.stems, draft.stems))
    kind = _share(sent.kind, draft.kind)
    if not tags and not kind:
        return 0.0
    value = tags + kind + _quantity_adjustment(sent.quantity, draft.quantity)
    return value if value >= MIN_SYSTEM_SCORE else 0.0


def _line_belongs(text: str, part: ScoreBlock) -> bool:
    normalized = normalize_tag(text)
    if any(tag and tag in normalized for tag in part.tags):
        return True
    if any(stem and stem in normalized for stem in part.stems):
        return True
    _, words = line_tokens(text)
    return bool(words & part.kind)


def _split_families(blocks: list[ScoreBlock]) -> list[ScoreBlock]:
    """A block printed as several stacked headers ("Qty (a) X / Qty (b) Y") split into one block per
    header, each free to match a different sent block. A line that names one part's tag, tag type or
    kind words is theirs; a line that names none, or more than one, goes to every part — the whole
    block's lines, when the lines can't be split."""
    out = []
    for block in blocks:
        if len(block.headers) <= 1:
            out.append(block)
            continue
        parts = [_block([header], []) for header in block.headers]
        buckets: list[list[tuple[str, int]]] = [[] for _ in parts]
        for line in block.lines:
            hits = [i for i, part in enumerate(parts) if _line_belongs(line[0], part)]
            for i in (hits or range(len(parts))):
                buckets[i].append(line)
        out += [_block(part.headers, lines) for part, lines in zip(parts, buckets)]
    return out


def _pairs(sent: list, draft: list, score) -> list[tuple[int, int, float]]:
    """One to one, the best-scoring pairs first."""
    scored = sorted(((score(s, d), i, j) for i, s in enumerate(sent) for j, d in enumerate(draft)),
                    key=lambda x: (-x[0], x[1], x[2]))
    used_s, used_d, out = set(), set(), []
    for value, i, j in scored:
        if value <= 0 or i in used_s or j in used_d:
            continue
        used_s.add(i)
        used_d.add(j)
        out.append((i, j, value))
    return out


def line_tokens(text: str) -> tuple[str, frozenset]:
    """(the house verb, the device words) of a line: quantities, brackets and punctuation taken off."""
    plain = squash(_BRACKETS.sub(" ", _LINE_QTY.sub(" ", text or ""))).casefold()
    plain = re.sub(r"[^a-z0-9/ ]+", " ", plain.replace("-", " "))
    plain = squash(plain.replace("/", " "))
    verb = next((v for v in _VERBS if plain == v or plain.startswith(v + " ")), "")
    rest = plain[len(verb):]
    words = frozenset(_singular(w) for w in rest.split() if w not in _STOP)
    return verb, words


def line_overlap(a: str, b: str) -> float:
    """The share of verb and device tokens two lines have in common (of the longer's)."""
    va, wa = line_tokens(a)
    vb, wb = line_tokens(b)
    ta = wa | ({f"verb:{va}"} if va else set())
    tb = wb | ({f"verb:{vb}"} if vb else set())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _line_score(sent: str, draft: str) -> float:
    value = line_overlap(sent, draft)
    return value if value >= LINE_OVERLAP else 0.0


def line_quantity(text: str) -> int | None:
    m = _LINE_QTY.search(text or "")
    return int(next(g for g in m.groups() if g)) if m else None


def _count(sent: int | None, draft: int | None) -> str:
    if sent is None:
        return ""
    return EQUAL if draft == sent else COUNT_DIFFERS


@dataclass
class Score:
    job: str
    systems: list[list] = field(default_factory=list)   # [sent header, draft header, status, sent qty, draft qty, count]
    lines: list[list] = field(default_factory=list)     # [system, sent line, draft line, status, overlap, sent qty,
                                                        #  draft qty, count]
    sent_systems: int = 0
    matched_systems: int = 0
    sent_lines: int = 0
    matched_lines: int = 0
    counts_equal: int = 0
    counts_compared: int = 0
    weak_systems: int = 0        # matched systems with no exact tag in common — by kind or tag type only

    @property
    def summary(self) -> str:
        return (f"systems {self.matched_systems}/{self.sent_systems}, lines {self.matched_lines}/{self.sent_lines}, "
                f"counts {self.counts_equal}/{self.counts_compared}")


def score(draft: list[ScoreBlock], sent: list[ScoreBlock], job: str = "") -> Score:
    draft = _split_families(draft)
    result = Score(job, sent_systems=len(sent), sent_lines=sum(len(b.lines) for b in sent))

    def counted(state: str) -> None:
        if state:
            result.counts_compared += 1
            result.counts_equal += state == EQUAL

    pairs = {i: j for i, j, _ in _pairs(sent, draft, _system_score)}
    for i, block in enumerate(sent):
        j = pairs.get(i)
        if j is None:
            result.systems.append([block.header, None, MISSING, block.quantity, None, None])
            for text, _ in block.lines:
                result.lines.append([block.header, text, None, MISSING, None, line_quantity(text), None, None])
            continue
        other = draft[j]
        state = _count(block.quantity, other.quantity)
        counted(state)
        result.matched_systems += 1
        if not (block.tags & other.tags):
            result.weak_systems += 1
        status = DIFFERS if state == COUNT_DIFFERS else MATCHED
        result.systems.append([block.header, other.header, status, block.quantity, other.quantity, state or None])
        sent_texts, draft_texts = [t for t, _ in block.lines], [t for t, _ in other.lines]
        matches = {a: (b, v) for a, b, v in _pairs(sent_texts, draft_texts, _line_score)}
        for a, text in enumerate(sent_texts):
            if a not in matches:
                result.lines.append([block.header, text, None, MISSING, None, line_quantity(text), None, None])
                continue
            b, value = matches[a]
            mine = draft_texts[b]
            same = line_tokens(text) == line_tokens(mine)
            quantities = (line_quantity(text), line_quantity(mine))
            state = _count(*quantities)
            counted(state)
            result.matched_lines += 1
            result.lines.append([block.header, text, mine, MATCHED if same else WORDED, round(value, 2),
                                 *quantities, state or None])
        taken = {b for b, _ in matches.values()}
        for b, mine in enumerate(draft_texts):
            if b not in taken:
                result.lines.append([block.header, None, mine, EXTRA, None, None, line_quantity(mine), None])
    for j, block in enumerate(draft):
        if j not in pairs.values():
            result.systems.append([None, block.header, EXTRA, None, block.quantity, None])
            for text, _ in block.lines:
                result.lines.append([block.header, None, text, EXTRA, None, None, line_quantity(text), None])
    return result


# --- the workbook -------------------------------------------------------------------------------------------------

_FILL = {MATCHED: "C6EFCE", WORDED: "FFEB9C", DIFFERS: "FFEB9C", MISSING: "FFC7CE", EXTRA: "D9D9D9",
         EQUAL: "C6EFCE", COUNT_DIFFERS: "FFC7CE"}
_BAD_FILENAME = re.compile(r'[<>:"/\\|?*]')


def job_name(draft: Path, sent: Path) -> str:
    """The job's number from the file names, else the draft's name without " Proposal"."""
    for path in (draft, sent):
        m = _JOB.search(Path(path).stem)
        if m:
            return m.group(0)
    return re.sub(r"\s*Proposal$", "", Path(draft).stem, flags=re.I).strip() or "job"


def _sheet(ws, headings: list[str], rows: list[list], status_col: int, widths: list[int]) -> None:
    ws.append(headings)
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True), PatternFill("solid", fgColor="D9E1F2")
    for row in rows:
        ws.append(row)
        for c in (status_col, len(headings)):
            value = ws.cell(ws.max_row, c).value
            if value in _FILL:
                ws.cell(ws.max_row, c).fill = PatternFill("solid", fgColor=_FILL[value])
        for c in range(1, len(headings) + 1):
            ws.cell(ws.max_row, c).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for n, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + n)].width = width


def write_score(result: Score, folder: Path) -> Path:
    book = Workbook()
    ws = book.active
    ws.title = "Summary"
    ws.append([f"Score — {result.job}"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([result.summary])
    ws.append([CAVEAT])
    ws.append([])
    for label, value in (("Systems in the sent proposal", result.sent_systems),
                         ("Found in the draft", result.matched_systems),
                         ("Lines in the sent proposal", result.sent_lines),
                         ("Found in the draft (matched or worded differently)", result.matched_lines),
                         ("Counts compared (block and line quantities the sent proposal states)", result.counts_compared),
                         ("Counts equal", result.counts_equal),
                         ("Systems matched by kind or tag type only (check these)", result.weak_systems)):
        ws.append([label, value])
    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 12
    _sheet(book.create_sheet("Systems"), ["Sent block", "Draft block", "Status", "Sent quantity", "Draft quantity",
                                          "Count"], result.systems, 3, [50, 50, 18, 13, 13, 10])
    _sheet(book.create_sheet("Lines"), ["Block", "Sent line", "Draft line", "Status", "Overlap", "Sent quantity",
                                        "Draft quantity", "Count"], result.lines, 4, [40, 60, 60, 18, 9, 13, 13, 10])
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_BAD_FILENAME.sub('-', result.job)} Score.xlsx"
    book.save(str(path))
    return path


def score_proposals(draft: Path, sent: Path, folder: Path) -> tuple[Path, Score]:
    result = score(read_blocks(draft), read_blocks(sent), job_name(draft, sent))
    return write_score(result, folder), result
