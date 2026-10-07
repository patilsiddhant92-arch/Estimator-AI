"""The job ledger's facts (design 2026-09-29 §1): each with its kind, subject, value, source, quote, the pass that
settled it and its state. A settled fact never changes its value; a different value from a later pass is a
contradiction kept beside it, and the printed count is the highest value among them.

Ids are stored without brackets ("S41", "Q7", "I2", "F17") however they were given."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

KINDS = ("family", "unit", "count", "location", "device", "provider", "link", "group", "sequence_match",
         "front_end", "note")
STAGES = ("seed", "schedules", "plans", "details", "risers", "network", "sequence", "spec")
SETTLED, ADDED, CONTRADICTED = "settled", "added", "contradicted"
STATES = (SETTLED, ADDED, CONTRADICTED)

_BRACKETS = re.compile(r"^\s*\[?\s*([A-Za-z]{1,4}\d+[a-z]?)\s*\]?\s*$")
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def plain_id(value) -> str:
    """"[S41]" or "S41" -> "S41"; anything else -> ""."""
    match = _BRACKETS.match(str(value or ""))
    return match.group(1) if match else ""


def where_short(where: str) -> str:
    """A source's place without the trailing parenthetical: "M-201, Drawings.pdf page 3"."""
    return _PAREN.sub("", where or "").strip()


@dataclass(frozen=True)
class Contradiction:
    value: object
    source_id: str
    quote: str
    stage: str


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str
    subject: str
    value: object
    source_id: str
    quote: str
    stage: str
    state: str = ADDED
    contradictions: tuple[Contradiction, ...] = ()
    # once settled, always so: a contradiction later turns a settled fact and an added one alike into
    # "contradicted", and only this tells a schedule's count from one seen on the plans alone
    was_settled: bool = False

    def line(self) -> str:
        """One line for a prompt or a tab: id, kind, subject, value, source, quote, state and pass, then each
        contradiction."""
        head = f"{self.id} {self.kind} {self.subject} = {self.value} [{self.source_id}] “{self.quote}”"
        tail = f"{self.state}, {self.stage}"
        for c in self.contradictions:
            tail += f"; {c.stage} says {c.value} [{c.source_id}] “{c.quote}”"
        return f"{head} ({tail})"


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        return int(text) if text.isdigit() else None
    except (TypeError, ValueError):
        return None


class Ledger:
    """The facts of one job, in the order they were added, with the understanding paragraph of each pass."""

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self.sources: dict[str, str] = dict(sources or {})
        self.facts: dict[str, Fact] = {}
        self.understanding: dict[str, str] = {}
        self.complete: bool = False
        self.stopped_at: str = ""
        self.job_name: str = ""
        self.refused: dict[str, list[str]] = {}     # per pass: what the answer said that could not be kept
        self._n = 0

    # --- adding and changing ------------------------------------------------------------------------

    def knows(self, source_id: str) -> bool:
        sid = plain_id(source_id)
        return bool(sid) and (sid in self.sources or sid in self.facts)

    def add(self, kind: str, subject: str, value, source_id: str, quote: str, stage: str, state: str = ADDED) -> Fact:
        if kind not in KINDS:
            raise ValueError(f"a fact's kind must be one of {', '.join(KINDS)}, not {kind!r}")
        if stage not in STAGES:
            raise ValueError(f"a fact's pass must be one of {', '.join(STAGES)}, not {stage!r}")
        if state not in STATES:
            raise ValueError(f"a fact's state must be one of {', '.join(STATES)}, not {state!r}")
        sid = plain_id(source_id)
        if not self.knows(sid):
            raise ValueError(f"the source {source_id!r} is not one the dossier or the ledger has")
        quote = " ".join(str(quote or "").split())
        if not quote:
            raise ValueError("a fact needs a quote: the words or numbers stating it")
        self._n += 1
        fact = Fact(f"F{self._n}", kind, " ".join(str(subject or "").split()), value, sid, quote, stage, state,
                    was_settled=state == SETTLED)
        self.facts[fact.id] = fact
        return fact

    def settle(self, fact_id: str) -> Fact:
        fact = self.facts[plain_id(fact_id) or fact_id]
        if fact.state == ADDED:
            fact = replace(fact, state=SETTLED, was_settled=True)
            self.facts[fact.id] = fact
        return fact

    def resolve(self, fact_id: str, value, source_id: str, quote: str, stage: str) -> Fact:
        """The pass that owns a provisional fact's kind gives its value: the fact takes that value, source, quote and
        pass, keeps its id and becomes settled. Only a fact still waiting (added) can be resolved."""
        fact = self.facts[plain_id(fact_id) or fact_id]
        if fact.state != ADDED:
            raise ValueError(f"{fact.id} is {fact.state}: only a fact still waiting for its pass can take a new value")
        if stage not in STAGES:
            raise ValueError(f"a fact's pass must be one of {', '.join(STAGES)}, not {stage!r}")
        sid = plain_id(source_id)
        if not self.knows(sid):
            raise ValueError(f"the source {source_id!r} is not one the dossier or the ledger has")
        quote = " ".join(str(quote or "").split())
        if not quote:
            raise ValueError("a fact needs a quote: the words or numbers stating it")
        fact = replace(fact, value=value, source_id=sid, quote=quote, stage=stage, state=SETTLED,
                       was_settled=True)
        self.facts[fact.id] = fact
        return fact

    def contradict(self, fact_id: str, value, source_id: str, quote: str, stage: str) -> Fact:
        """A different value for a fact, kept beside it with its own source; the fact's value stays."""
        fact = self.facts[plain_id(fact_id) or fact_id]
        if str(value) == str(fact.value) or any(str(c.value) == str(value) for c in fact.contradictions):
            return fact
        sid = plain_id(source_id)
        if not self.knows(sid):
            raise ValueError(f"the source {source_id!r} is not one the dossier or the ledger has")
        quote = " ".join(str(quote or "").split())
        if not quote:
            raise ValueError("a contradiction needs a quote: the words or numbers stating the other value")
        fact = replace(fact, state=CONTRADICTED,
                       contradictions=fact.contradictions + (Contradiction(value, sid, quote, stage),))
        self.facts[fact.id] = fact
        return fact

    # --- reading ------------------------------------------------------------------------------------

    def printed_count(self, fact_id: str) -> int | None:
        """The highest number among a fact's value and its contradictions; None when none is a number."""
        fact = self.facts[plain_id(fact_id) or fact_id]
        numbers = [n for n in (_number(fact.value), *(_number(c.value) for c in fact.contradictions)) if n is not None]
        return max(numbers) if numbers else None

    def of_kind(self, kind: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.kind == kind]

    def about(self, subject: str) -> list[Fact]:
        key = subject.casefold()
        return [f for f in self.facts.values() if f.subject.casefold() == key]

    def find(self, kind: str, subject: str) -> Fact | None:
        key = subject.casefold()
        return next((f for f in self.facts.values() if f.kind == kind and f.subject.casefold() == key), None)

    def find_value(self, kind: str, subject: str, value) -> Fact | None:
        """The fact of this kind and subject holding this value (the subject in any case, the value word for word
        once its spaces are squashed); None when there is none."""
        key, wanted = subject.casefold(), " ".join(str(value).split())
        return next((f for f in self.facts.values() if f.kind == kind and f.subject.casefold() == key
                     and " ".join(str(f.value).split()) == wanted), None)

    def table(self, fact_ids=None) -> str:
        facts = self.facts.values() if fact_ids is None else [self.facts[plain_id(i) or i] for i in fact_ids
                                                                if (plain_id(i) or i) in self.facts]
        return "\n".join(f.line() for f in facts)

    # --- saving ---------------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"version": 1, "job_name": self.job_name, "sources": self.sources, "complete": self.complete,
                "stopped_at": self.stopped_at, "understanding": self.understanding, "refused": self.refused,
                "facts": [asdict(f) for f in self.facts.values()]}

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        ledger = cls(data.get("sources") or {})
        ledger.complete = bool(data.get("complete"))
        ledger.stopped_at = str(data.get("stopped_at") or "")
        ledger.job_name = str(data.get("job_name") or "")
        ledger.understanding = dict(data.get("understanding") or {})
        ledger.refused = {k: list(v) for k, v in (data.get("refused") or {}).items()}
        for raw in data.get("facts") or []:
            fact = Fact(raw["id"], raw["kind"], raw["subject"], raw["value"], raw["source_id"], raw["quote"],
                        raw["stage"], raw.get("state", ADDED),
                        tuple(Contradiction(**c) for c in raw.get("contradictions") or ()),
                        # a ledger saved before the mark: read its state as today's planners did
                        bool(raw.get("was_settled", raw.get("state", ADDED) != ADDED)))
            ledger.facts[fact.id] = fact
            ledger._n = max(ledger._n, int(fact.id[1:]))
        return ledger

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
