"""Held-out measurement (workstream 7, design §4.8): match the rendered lines to the estimator's final proposal.

    python tools/measure.py JOB.json_OR_OUT_FOLDER FINAL_PROPOSAL.docx

The first argument is a Job JSON (such as `<quote> Job.json`), an out folder holding one, or a JSON list of rendered
lines. Used on the held-out jobs only, to see whether a change helped; never to tune. Prints the share matched, then
the missed and the extra lines. Runs on this machine only and writes nothing into the repo.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bms.render import RenderedLine  # noqa: E402


@dataclass(frozen=True)
class LineMatch:
    system: str                 # the system / block header as printed
    device: str                 # the device words
    verb: str | None
    quantity: int | None


@dataclass(frozen=True)
class MeasureResult:
    matched: tuple[tuple[LineMatch, LineMatch], ...]   # (rendered, final) pairs
    missed: tuple[LineMatch, ...]                      # in the final proposal, not rendered
    extra: tuple[LineMatch, ...]                       # rendered, not in the final proposal

    @property
    def share_matched(self) -> float:
        total = len(self.matched) + len(self.missed)
        return len(self.matched) / total if total else 1.0

    def summary(self) -> str:
        """One line: "matched a/b (p%), missed c, extra d"."""
        total = len(self.matched) + len(self.missed)
        return (f"matched {len(self.matched)}/{total} ({self.share_matched:.0%}), missed {len(self.missed)}, "
                f"extra {len(self.extra)}")


# ---- reading lines ----------------------------------------------------------------------------------------------

_STOP = {"and", "of", "the", "a", "an", "to", "for", "by", "with", "in", "on", "at", "or", "via", "per"}
_VERB_FORMS = ("furnish and install", "install and wire", "furnish and wire", "furnish", "install", "wire")
_QTY_PREFIX = re.compile(r"^\s*(?:qty\s*)?\(\s*(?:x\s*)?(?:\d+|#+)\s*\)\s*", re.IGNORECASE)
_QTY_ANY = re.compile(r"(?:\bqty\s*)?\(\s*(?:x\s*)?(\d+|#+)\s*\)|\bx\s*(\d+)\b|\bqty\s*(\d+)\b", re.IGNORECASE)
_BRACKETS = re.compile(r"\[[^\]]*\]|\(\s*(?:by|furnished|provided)[^)]*\)", re.IGNORECASE)
FRONT_END = "Front End"
SYSTEM_MIN = 0.34       # word overlap (shared / all) two system names need to be the same system
DEVICE_MIN = 0.5        # the same for device words


def _words(text: str) -> frozenset[str]:
    """Lower-case words with a plural "s" folded, stop words dropped."""
    out = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in _STOP:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add(word)
    return frozenset(out)


def _split_line(text: str) -> tuple[str | None, int | None, str]:
    """(verb, quantity, device words) from a printed line: the verb at the start, a "(N)" / "Qty (N)" / "xN"
    quantity, owner brackets and "*" dropped. A "(##)" quantity is unknown (None)."""
    rest = text.strip().lstrip("*").strip()
    verb = None
    low = rest.lower()
    for form in _VERB_FORMS:
        if low == form or low.startswith(form + " "):
            verb = form
            rest = rest[len(form):].lstrip(" :-")
            break
    quantity = None
    found = _QTY_ANY.search(rest)
    if found:
        number = next((g for g in found.groups() if g), None)
        quantity = int(number) if number and number.isdigit() else None
        rest = rest[:found.start()] + " " + rest[found.end():]
    rest = _BRACKETS.sub(" ", rest)
    return verb, quantity, re.sub(r"\s+", " ", rest).strip()


def _canon_verb(verb: str | None) -> str | None:
    return verb.lower().strip() if verb else None


def _strip_header(text: str) -> str:
    return _QTY_PREFIX.sub("", text).strip()


def _rendered_matches(lines: Sequence[RenderedLine]) -> list[LineMatch]:
    names: dict[str, str] = {}
    for line in lines:
        if line.kind == "header" and line.system_key not in names:
            names[line.system_key] = _strip_header(line.text)
    out = []
    for line in lines:
        if line.kind != "line":
            continue
        system = names.get(line.system_key) or (FRONT_END if line.system_key == "" else line.system_key)
        text_verb, _q, device = _split_line(line.text)
        out.append(LineMatch(system, device, _canon_verb(line.verb) or text_verb, line.quantity))
    return out


def _final_matches(path: Path) -> list[LineMatch]:
    from estimator.files import open_docx
    from estimator.proposal.read import read_scope

    _suffix, front, blocks, add, deduct = read_scope(open_docx(path))
    out: list[LineMatch] = []

    def take(system: str, items) -> None:
        for item in items:
            if item.kind != "line":
                continue
            verb, qty, device = _split_line(item.text)
            out.append(LineMatch(system, device, verb, qty))

    take(FRONT_END, front.items)
    for block in (*blocks, *(b for alt in (*add, *deduct) for b in alt.blocks)):
        take(_strip_header(block.header), block.items)
    return out


# ---- matching ---------------------------------------------------------------------------------------------------


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _agree(rendered: LineMatch, final: LineMatch) -> bool:
    """Verb and quantity agree; a final line that prints no verb or no quantity asks for none."""
    if final.verb and rendered.verb and _canon_verb(final.verb) != _canon_verb(rendered.verb):
        return False
    if final.quantity is not None and rendered.quantity != final.quantity:
        return False
    return True


def match_lines(rendered: Sequence[LineMatch], final: Sequence[LineMatch]) -> MeasureResult:
    """Match each final line to at most one rendered line: the same system, device words alike, verb and quantity
    agreeing; the closest device words first."""
    pairs = []
    for i, r in enumerate(rendered):
        for j, f in enumerate(final):
            if r.system != f.system and _overlap(r.system, f.system) < SYSTEM_MIN:
                continue
            score = _overlap(r.device, f.device)
            if score >= DEVICE_MIN and _agree(r, f):
                pairs.append((-score, i, j))
    pairs.sort()
    used_r: set[int] = set()
    used_f: set[int] = set()
    taken = []
    for _neg, i, j in pairs:
        if i in used_r or j in used_f:
            continue
        used_r.add(i)
        used_f.add(j)
        taken.append((i, j))
    taken.sort()
    return MeasureResult(
        tuple((rendered[i], final[j]) for i, j in taken),
        tuple(f for j, f in enumerate(final) if j not in used_f),
        tuple(r for i, r in enumerate(rendered) if i not in used_r))


def measure(rendered_lines: Sequence[RenderedLine], final_proposal_path: Path) -> MeasureResult:
    """Match each device line of `rendered_lines` (`bms.render.RenderedLine`, kind "line") to a line of the final
    proposal (read with `estimator.proposal.read.read_scope`) on system, device words, verb and quantity; one
    final line matches at most one rendered line. Notes, headers and clarifications are not measured."""
    return match_lines(_rendered_matches(rendered_lines), _final_matches(Path(final_proposal_path)))


# ---- command line -----------------------------------------------------------------------------------------------


def _rendered_from(source: Path) -> list[RenderedLine]:
    """The rendered lines of a job file, an out folder holding `<quote> Job.json`, or a JSON list of lines."""
    import json

    from bms.model import Job
    from bms.playbook import load_playbook
    from bms.render import render

    path = Path(source)
    if path.is_dir():
        found = sorted(path.glob("* Job.json")) or sorted(path.glob("*Job.json"))
        if not found:
            raise SystemExit(f"no Job.json in {path}")
        path = found[0]
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return [RenderedLine(**row) for row in data]
    return list(render(Job.from_dict(data), load_playbook()).lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(args) != 2:
        print("usage: python tools/measure.py <job.json or out folder> <final.docx>")
        return 2
    result = measure(_rendered_from(Path(args[0])), Path(args[1]))
    print(result.summary())
    for label, rows in (("missed", result.missed), ("extra", result.extra)):
        for row in rows:
            qty = "Qty (##)" if row.quantity is None else row.quantity
            print(f"  {label}: [{row.system}] {row.verb or '-'} | {row.device} | {qty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
