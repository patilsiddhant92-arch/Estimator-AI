"""FINAL-J (the lead's ruling on FINAL-H concern 1): a ledger source's sheet number (`Job.source_sheets`) is a known
sheet only in a writer's where and in client text right after a sheet word ("per sheet S201", "sheets S201 and
S202"). A bare issued id in client text ("Valves per S201.") stays refused at intake, must_fix at validate and cut at
render even when it is also a source sheet: it may be the source id the writer printed. The planner's own sheets (K,
`job_sheets`) keep their behaviour: a sheet wherever they stand.

Every probe goes through the real intake (`ai._check_system`, given K and the source sheets as the run gives them),
the validator and the renderer on one job, so all three read the same I, T, K and source sheets. Rows marked GUARD
pin behaviour that is unchanged from rebuild 36b6d5c (they pass there too); every other row fails there. Invented
fixture and invented job folder only."""
from __future__ import annotations

from dataclasses import replace

import pytest

from bms import ai, run
from bms.citations import SourceIds, job_ids, job_sheets, job_tags
from bms.model import Job
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, ZERO_WIDTH, _job, _prints, _with_note, _with_other_count
from test_run import answer_all, job_folder  # noqa: F401  (job_folder is a fixture)

REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")
SOURCE = ("S201", "S202")             # the job's source sheets; both are issued ids of the test job too (EXTRA)
ZW = ZERO_WIDTH[0]


def _verdicts(kind: str, probe: str, token: str, source=SOURCE, planner=(), tag=None) -> tuple[str, str, str]:
    """(intake, validator, render) for `probe` as EF's note (text) or a typed where (where)."""
    job = replace(_job(planner, tag), source_sheets=tuple(source))
    job = _with_note(job, probe) if kind == "text" else _with_other_count(job, probe)
    system = job.system("EF")
    written, _ = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                  job_tags(job), job_ids(job), tuple(job_sheets(job)), tuple(job.source_sheets))
    severities = [f.severity for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.system_key == "EF"]
    return ("refused" if written is None else "accepted", "must_fix" if "must_fix" in severities else "none",
            "prints" if _prints(job, token) else "cut")


# (kind, probe, the token looked for in print, source sheets, planner K, a tag, verdict, GUARD)
PROBES = [
    # client text: a bare source sheet that is an issued id stays an issued id (new)
    ("text", "Valves per S201.", "S201", SOURCE, (), None, REFUSED, False),
    ("text", "See S201 for the valves.", "S201", SOURCE, (), None, REFUSED, False),
    ("text", "S201 valves on the roof.", "S201", SOURCE, (), None, REFUSED, False),
    ("text", "Valves per s201.", "s201", SOURCE, (), None, REFUSED, False),
    ("text", "Valves per Ｓ201.", "S201", SOURCE, (), None, REFUSED, False),               # full-width S
    ("text", f"Valves per S{ZW}201.", "S201", SOURCE, (), None, REFUSED, False),          # zero-width inside
    ("text", "Valves (S201).", "S201", SOURCE, (), None, REFUSED, False),
    ("text", "Valves per S201 and S202.", "S202", SOURCE, (), None, REFUSED, False),
    ("text", "Valves per S201 and S999.", "S201", SOURCE, (), None, REFUSED, False),      # S999 cited along
    ("text", "Valves per sheet S201, see S202.", "S202", SOURCE, (), None, REFUSED, False),  # S202 bare
    ("text", "Valves per S201 (sheet).", "S201", SOURCE, (), None, REFUSED, False),       # a sheet word after
    # client text: right after a sheet word a source sheet is a sheet (GUARD: FINAL-H accepted these too)
    ("text", "Valves per sheet S201.", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per Sheet No. S201.", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per (sheet S201).", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per sheet s201.", "s201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per dwg. S201.", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per sheet: S201.", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves per sheet Ｓ201.", "S201", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves on sheets S201 and S202.", "S202", SOURCE, (), None, ACCEPTED, True),
    ("text", "Valves on sheets S201, S202.", "S202", SOURCE, (), None, ACCEPTED, True),
    # client text: unchanged rules (GUARD)
    ("text", "Valves on sheets S201 and S141.", "S141", SOURCE, (), None, REFUSED, True),   # S141 no sheet (L-D)
    ("text", "Valves per sheet S141.", "S141", SOURCE, (), None, REFUSED, True),
    ("text", "Valves on sheets S201 thru S203.", "S203", SOURCE, (), None, REFUSED, True),  # S203 issued, no sheet
    ("text", "Valves per S141.", "S141", SOURCE, ("S141",), None, ACCEPTED, True),          # a planner sheet: bare too
    ("text", "Valves per S777.", "S777", ("S777",), (), None, ACCEPTED, True),              # never issued: loose
    ("text", "Valves per S201.", "S201", SOURCE, (), "S201", ACCEPTED, True),               # a real tag of the job
    ("text", "Valves per S201.", "S201", (), (), None, REFUSED, True),                      # no source sheet at all
    # a typed where: a source sheet is a sheet wherever it stands in it (GUARD: FINAL-H)
    ("where", "S201, Structural.pdf page 3", "S201", SOURCE, (), None, ACCEPTED, True),
    ("where", "Sheet S201, Structural.pdf page 3", "S201", SOURCE, (), None, ACCEPTED, True),
    ("where", "s201, Structural.pdf page 3", "s201", SOURCE, (), None, ACCEPTED, True),
    ("where", "Ｓ201, Structural.pdf page 3", "S201", SOURCE, (), None, ACCEPTED, True),
    ("where", "Structural schedule, S201", "S201", SOURCE, (), None, ACCEPTED, True),
    ("where", "S141, Structural.pdf page 3", "S141", SOURCE, (), None, REFUSED, True),      # issued, no sheet
    ("where", "Sheet S141, Structural.pdf page 3", "S141", SOURCE, (), None, REFUSED, True),
    ("where", "Sheet S201 and S141, Structural.pdf page 3", "S141", SOURCE, (), None, REFUSED, True),
    ("where", "S201, Structural.pdf page 3", "S201", (), (), None, REFUSED, True),           # no source sheet
]


@pytest.mark.parametrize("kind, probe, token, source, planner, tag, verdict, guard", PROBES,
                         ids=[f"{'GUARD-' if p[7] else ''}{p[0]}-{n}" for n, p in enumerate(PROBES)])
def test_intake_validator_and_render_agree_on_a_source_sheet(kind, probe, token, source, planner, tag, verdict,
                                                               guard):
    assert _verdicts(kind, probe, token, source, planner, tag) == verdict


def test_guard_probe_table_shape():
    """GUARD: checks only the table itself (its size and mix), no behaviour; it passes on rebuild too."""
    assert len(PROBES) >= 30
    assert sum(1 for p in PROBES if not p[7]) >= 10          # rows that fail on rebuild 36b6d5c
    assert {p[0] for p in PROBES} == {"text", "where"}


def test_the_detector_reads_a_source_sheet_by_where_it_stands():
    """One detector, two readings: in client text a source sheet is issued unless a sheet word comes before it; in
    a where (and a text made of places) it is a sheet anywhere; K is a sheet everywhere."""
    ids = SourceIds.of(("S201", "S141", "S300"), (), ("S300",), source_sheets=("s201",))
    assert ids.source_sheets == frozenset({"S201"}) and ids.sheets == frozenset({"S300"})
    assert [f.kind for f in ids.scan("per S201")] == ["issued"]
    assert [f.kind for f in ids.scan("per sheet S201")] == ["sheet"]
    assert [f.kind for f in ids.scan("per S300")] == ["sheet"]
    assert ids.refusal("per S201") and not ids.refusal("per sheet S201")
    assert ids.without_issued("Valves per S201 here") == "Valves per here"
    assert ids.without_issued("(2) per M-001; 1 per S201", place=True) == "(2) per M-001; 1 per S201"
    assert ids.without_issued("(2) per M-001; 1 per S141", place=True) == "(2) per M-001; 1 per"
    assert ids.where_issued("Structural schedule, S201") == []
    assert ids.where_issued("S141, Structural.pdf page 3") == ["S141"]
    assert ids.place("S201, Structural.pdf page 3") == "S201"
    assert ids.is_id("S201") and not ids.is_id("S300")      # a source sheet is still an issued id


def test_the_job_detector_keeps_k_and_the_source_sheets_apart():
    job = replace(_job(("S141",)), source_sheets=("S201",))
    assert job_sheets(job) == frozenset({"S141"})
    ids = SourceIds.of_job(job)
    assert ids.sheets == frozenset({"S141"}) and ids.source_sheets == frozenset({"S201"})


def test_a_text_full_of_source_sheets_is_read_in_linear_time():
    from timing import grows_linearly
    ids = SourceIds.of([f"S{k}" for k in range(1, 400)], (), (), source_sheets=[f"S{k}" for k in range(1, 400)])
    assert grows_linearly(lambda n: ids.refusal(" and ".join(f"S{k % 399 + 1}" for k in range(n))), 2000)
    assert grows_linearly(lambda n: ids.where_issued(", ".join(f"S{k % 399 + 1}" for k in range(n))), 2000)


def test_the_run_passes_the_source_sheets_beside_k_to_every_writer(job_folder, tmp_path, monkeypatch):  # noqa: F811
    """The run's writers get the job's source sheets as `source_sheets`, never inside `sheets` (K), so the intake
    reads them as the validator and the renderer do."""
    real_ledger, real_write = run.read_ledger, ai.write_system
    seen: list[tuple[tuple, tuple]] = []

    def reading(*args, **kwargs):
        ledger = real_ledger(*args, **kwargs)
        ledger.sources["S900"] = "S201, Structural.pdf page 3"
        return ledger

    def writing(*args, **kwargs):
        seen.append((tuple(kwargs.get("sheets", ())), tuple(kwargs.get("source_sheets", ()))))
        return real_write(*args, **kwargs)

    monkeypatch.setattr(run, "read_ledger", reading)
    monkeypatch.setattr(ai, "write_system", writing)
    out, cache = tmp_path / "out", tmp_path / "cache"
    for _ in range(40):
        result = run.estimate(job_folder, out, cache, "chat")
        if result.status == "done":
            break
        assert result.status == "waiting" and answer_all(cache), result.messages
    else:
        raise AssertionError("the run never finished")
    assert seen
    assert all("S201" in source and "S201" not in sheets for sheets, source in seen)
    saved = Job.from_json(result.job_file.read_text(encoding="utf-8"))
    assert "S201" not in job_sheets(saved) and "S201" in SourceIds.of_job(saved).source_sheets
