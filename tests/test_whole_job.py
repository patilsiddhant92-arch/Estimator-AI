"""The whole-job judge: the reading passes ask through it, and one pass per planned system writes its scope
(the systems come from the job ledger). Every test uses a fake client: no test touches the network."""
import json
from types import SimpleNamespace

from estimator.writing.judge import CHAT_MODEL, Judge, TechHoursHint
from estimator.writing.templates import load_templates
from estimator.writing.whole_job import WRITE_PROMPT, PlannedSystem, WrittenLine, WrittenScope, checklist_text

DOSSIER = """1. Job
[S1] Somerville HS New Gym. Controls: new BACnet system.

2. Sequence of operation
[S2] A. Rooftop units RTU-1 thru 3 shall run on the BMS schedule.
[S3] B. Exhaust fans EF-1 and EF-2 shall be interlocked with RTU-1.

4. Schedules
[S4] RTU SCHEDULE (M-601, page 12): RTU-1 | 5000 CFM ; RTU-2 | 5000 CFM ; RTU-3 | 4000 CFM
[S5] UNIT HEATER SCHEDULE: UH-1 | QUANTITY 4 | INTEGRAL THERMOSTAT

5. Equipment counts
[S6] RTU: 3 schedule rows, 3 distinct tags.
"""
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _system(**overrides):
    system = {
        "key": "RTU-1-3", "header": "Rooftop Unit RTU-1 thru 3", "kind": "Packaged ERU / RTU / AHU",
        "tags": ["RTU-1", "RTU-2", "RTU-3"], "quantity": 3, "quantity_source": "[S4]",
        "quantity_quote": "RTU-1 | 5000 CFM ; RTU-2 | 5000 CFM ; RTU-3 | 4000 CFM",
        "sequence_sources": ["[S2]"], "schedule_sources": ["S4"], "group": "", "alternate": "",
        "exception": "", "why": "The schedule lists three rooftop units and the sequence runs them."}
    system.update(overrides)
    return system


def _response(answer, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(answer))],
        stop_reason=stop_reason, model=model)


class FakeClient:
    """Stands in for anthropic.Anthropic: records each call and hands back the next canned reply."""

    def __init__(self, *replies, stream=False):
        self.calls = []
        self._replies = list(replies) or [_response({})]
        self.messages = SimpleNamespace(create=self._create)
        if stream:
            self.messages.stream = self._stream

    def _next(self, kwargs):
        self.calls.append(kwargs)
        return self._replies[min(len(self.calls), len(self._replies)) - 1]

    def _create(self, **kwargs):
        return self._next(kwargs)

    def _stream(self, **kwargs):
        reply = self._next(kwargs)

        class _Manager:
            def __enter__(self_inner):
                return SimpleNamespace(get_final_message=lambda: reply)

            def __exit__(self_inner, *exc):
                return False

        return _Manager()


def _images(tmp_path):
    path = tmp_path / "H601.png"
    path.write_bytes(PNG)
    return [SimpleNamespace(path=str(path), what="H601 HVAC SCHEDULES — picture schedule", sheet="H601",
                            document="Drawings.pdf", page=7)]


def _judge(tmp_path, client=None, **kwargs):
    return Judge(tmp_path / "cache", model="test-model", client=client, **kwargs)


def test_the_checklist_names_every_master_template_system_on_one_line_each():
    templates = load_templates()
    text = checklist_text(templates)
    lines = text.splitlines()

    assert len(lines) == len(templates)
    for template, line in zip(templates, lines):
        assert line.startswith(f"- {template.name}")
    assert "tech hour" not in text.lower()
    assert "VAV" in lines[0]


# --- B2: write_system ----------------------------------------------------------------------------------

EVIDENCE = """[S2] A. Rooftop units RTU-1 thru 3 shall run on the BMS schedule.
[S7] Each rooftop unit shall report its discharge air temperature and a filter alarm.
Counts: RTU — 3 schedule rows, 3 distinct tags. Devices: SD (duct smoke detector) 3.
"""
OPTIONS = ["Furnish BMS Communication Wiring to Rooftop Unit Factory Controls",
           "Map Available Points Via Mfr. Provided BMS Interface",
           "Furnish and Install Duct Smoke Detector"]
EXAMPLES = [{"job": "25-0101", "header": "Qty (2) Rooftop Unit RTU-1, 2",
             "lines": [{"text": "Furnish BMS Communication Wiring to Rooftop Unit Factory Controls", "depth": 1}],
             "notes": ["**Start/Stop via BMS schedule"]}]


def _planned(**overrides):
    fields = dict(key="RTU-1-3", header="Rooftop Unit RTU-1 thru 3", kind="Packaged ERU / RTU / AHU",
                  tags=("RTU-1", "RTU-2", "RTU-3"), quantity=3, quantity_source="[S4]",
                  quantity_quote="RTU-1 | 5000 CFM ; RTU-2 | 5000 CFM ; RTU-3 | 4000 CFM",
                  sequence_sources=("[S2]", "[S7]"), schedule_sources=("[S4]",), group="", alternate="",
                  exception="", why="The schedule lists three rooftop units.")
    fields.update(overrides)
    return PlannedSystem(**fields)


def _line(text, depth=1, quantity=None, quote="shall run on the BMS schedule", source_id="[S2]",
          why="The sequence runs the units on the BMS.", confidence=0.9):
    return {"text": text, "depth": depth, "quantity": quantity, "quote": quote, "source_id": source_id,
            "why": why, "confidence": confidence}


def _scope_answer(**overrides):
    answer = {
        "lines": [
            _line(OPTIONS[0]),
            _line(OPTIONS[1], quote="report its discharge air temperature and a filter alarm", source_id="S7"),
            _line("Discharge Air Temperature", depth=2, quote="discharge air temperature", source_id="[S7]"),
        ],
        "client_notes": ["**Start/Stop via BMS schedule"],
        "tech_hours": {"per": "unit", "hours": 4, "like": "Packaged ERU / RTU / AHU"},
        "review_notes": ["Left out the duct smoke detector: the evidence shows none in the units."],
    }
    answer.update(overrides)
    return answer


def _write(tmp_path, client, images=(), system=None, **kwargs):
    return _judge(tmp_path, client, **kwargs).write_system(system or _planned(), EVIDENCE, images, OPTIONS,
                                                            EXAMPLES, "STYLE TEXT")


def test_the_scope_is_read_into_written_lines(tmp_path):
    scope = _write(tmp_path, FakeClient(_response(_scope_answer())))

    assert isinstance(scope, WrittenScope)
    assert scope.model == "claude-opus-5-5"
    first, second, third = scope.lines
    assert first == WrittenLine(text=OPTIONS[0], depth=1, quantity=None, quote="shall run on the BMS schedule",
                                source_id="[S2]", why="The sequence runs the units on the BMS.", confidence=0.9)
    assert second.source_id == "[S7]"
    assert third.depth == 2 and third.text == "Discharge Air Temperature"
    assert scope.client_notes == ("**Start/Stop via BMS schedule",)
    assert scope.tech_hours_hint == TechHoursHint("unit", 4.0, "Packaged ERU / RTU / AHU")
    assert scope.review_notes == ("Left out the duct smoke detector: the evidence shows none in the units.",)
    assert scope.refused == ()


def test_the_scope_request_carries_the_plan_evidence_and_the_template_in_the_gems_words(tmp_path):
    fake = FakeClient(_response(_scope_answer()))
    _write(tmp_path, fake, images=_images(tmp_path))

    (call,) = fake.calls
    assert call["system"] == WRITE_PROMPT
    schema = call["output_config"]["format"]["schema"]
    assert set(schema["required"]) >= {"lines", "client_notes", "tech_hours", "review_notes"}
    assert "source_id" in schema["properties"]["lines"]["items"]["required"]
    content = call["messages"][0]["content"]
    text = "\n".join(block["text"] for block in content if block["type"] == "text")
    for part in ("Rooftop Unit RTU-1 thru 3", "RTU-1, RTU-2, RTU-3", "[S4]", EVIDENCE.strip(), *OPTIONS,
                 "H601 HVAC SCHEDULES", "The Standard Template defines the ORDER OF CATEGORIES"):
        assert part in text
    assert "25-0101" not in text and "STYLE TEXT" not in text      # the GEM decides the wording
    assert [block["type"] for block in content].count("image") == 1


def test_a_streaming_client_is_used_when_it_has_one(tmp_path):
    fake = FakeClient(_response(_scope_answer()), stream=True)
    scope = _write(tmp_path, fake)

    assert scope is not None and len(scope.lines) == 3
    assert fake.calls[0]["max_tokens"] >= 32000


def test_the_write_prompt_asks_for_sources_quotes_and_reference_lines():
    low = WRITE_PROMPT.lower()
    for words in ("source_id", "quote", "reference line", "review_notes", "never invent a number"):
        assert words in low, words


def test_lines_that_break_the_house_style_are_refused(tmp_path):
    answer = _scope_answer()
    answer["lines"] += [_line("Some wiring maybe"), _line("Furnish and Install Sensor (4 tech hours)"),
                        _line("Furnish and Install Filter Switch, CONFIRMED")]
    answer["client_notes"] += ["no stars here", "**$500 allowance"]
    scope = _write(tmp_path, FakeClient(_response(answer)))

    # the GEM's words stand: only what the client must never see is refused (the GEM round)
    assert [l.text for l in scope.lines] == [OPTIONS[0], OPTIONS[1], "Discharge Air Temperature", "Some wiring maybe"]
    assert len(scope.refused) == 4
    assert scope.client_notes == ("**Start/Stop via BMS schedule",)


def test_a_quantity_with_no_quote_keeps_the_line_but_not_the_number(tmp_path):
    answer = _scope_answer()
    answer["lines"].append(_line("Furnish and Install Duct Smoke Detector", quantity=3, quote=""))
    scope = _write(tmp_path, FakeClient(_response(answer)))

    smoke = scope.lines[-1]
    assert smoke.text == "Furnish and Install Duct Smoke Detector"
    assert smoke.quantity is None and smoke.confidence <= 0.5
    assert any("3" in r and "Duct Smoke Detector" in r for r in scope.refused)


def test_a_line_with_no_quote_is_kept_with_low_confidence_and_a_bad_source_is_cleared(tmp_path):
    answer = _scope_answer()
    answer["lines"][0].update(quote="", confidence=0.95)
    answer["lines"][1].update(source_id="[S999]")
    scope = _write(tmp_path, FakeClient(_response(answer)))

    assert scope.lines[0].confidence == 0.5
    assert scope.lines[1].source_id == ""
    assert any("S999" in r for r in scope.refused)


def test_a_line_too_deep_for_its_place_is_raised(tmp_path):
    answer = _scope_answer(lines=[_line("Discharge Air Temperature Sensor", depth=3),
                                  _line(OPTIONS[0], depth=1), _line("Filter Alarm", depth=4)])
    scope = _write(tmp_path, FakeClient(_response(answer)))

    assert [(l.text, l.depth) for l in scope.lines] == [("Discharge Air Temperature Sensor", 1), (OPTIONS[0], 1),
                                                         ("Filter Alarm", 2)]


def test_unknown_fields_are_ignored_and_bad_tech_hours_dropped(tmp_path):
    answer = _scope_answer(mood="happy", tech_hours={"per": "fortnight", "hours": 4, "like": "RTU"})
    answer["lines"][0]["colour"] = "red"
    scope = _write(tmp_path, FakeClient(_response(answer)))

    assert len(scope.lines) == 3
    assert scope.tech_hours_hint is None
    assert any("tech hours" in r for r in scope.refused)


def test_the_same_scope_is_answered_from_the_cache(tmp_path):
    fake = FakeClient(_response(_scope_answer()))
    judge = _judge(tmp_path, fake)
    first = judge.write_system(_planned(), EVIDENCE, (), OPTIONS, EXAMPLES, "STYLE TEXT")
    second = judge.write_system(_planned(), EVIDENCE, (), OPTIONS, EXAMPLES, "STYLE TEXT")

    assert len(fake.calls) == 1 and (judge.calls, judge.cached) == (1, 1)
    assert second == first


def test_in_the_chat_the_scope_request_says_its_kind_and_lists_the_pictures(tmp_path):
    images = _images(tmp_path)
    judge = _judge(tmp_path, mode="chat")
    assert judge.write_system(_planned(), EVIDENCE, images, OPTIONS, EXAMPLES, "STYLE TEXT") is None

    (request_file,) = judge.requests_dir.glob("*.json")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert request["kind"] == "write_system"
    assert request["system"] == "Rooftop Unit RTU-1 thru 3"
    assert request["key"] == request_file.stem
    assert request["images"][0]["path"] == images[0].path
    assert "lines" in request["schema"]["properties"]

    judge.answers_dir.mkdir(parents=True)
    (judge.answers_dir / request_file.name).write_text(json.dumps(_scope_answer()), encoding="utf-8")
    scope = _judge(tmp_path, mode="chat").write_system(_planned(), EVIDENCE, images, OPTIONS, EXAMPLES,
                                                       "STYLE TEXT")
    assert scope is not None and scope.model == CHAT_MODEL and len(scope.lines) == 3


def test_the_options_may_be_a_master_template(tmp_path):
    template = next(t for t in load_templates() if t.name == "Exhaust Fan")
    fake = FakeClient(_response(_scope_answer()))
    _judge(tmp_path, fake).write_system(_planned(), EVIDENCE, (), template, EXAMPLES, "STYLE TEXT")

    text = fake.calls[0]["messages"][0]["content"][0]["text"]
    assert all(line.text in text for line in template.lines)


def test_no_key_means_no_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = _judge(tmp_path)
    assert judge.write_system(_planned(), EVIDENCE, (), OPTIONS, EXAMPLES, "STYLE TEXT") is None
    assert "no AI key" in judge.last_error


# --- round 3, Part B: the questions ---------------------------------------------------------------------------

def test_the_write_prompt_consolidates_identical_lines_with_totals_in_the_gems_order():
    for words in ("CONSOLIDATING IDENTICAL SCOPE LINES", "Default format: (Qty. ## Total)", "SOW ORDER — STANDARD TEMPLATE",
                  "tech-hour rule given"):
        assert words in WRITE_PROMPT, words


def test_the_scope_request_carries_the_templates_tech_hour_rule(tmp_path):
    fake = FakeClient(_response(_scope_answer()))
    _judge(tmp_path, fake).write_system(_planned(), EVIDENCE, (), OPTIONS, EXAMPLES, "STYLE TEXT",
                                        hours_rule="Packaged ERU / RTU / AHU: 16 h per unit")
    (call,) = fake.calls
    text = "\n".join(block["text"] for block in call["messages"][0]["content"] if block["type"] == "text")
    assert "tech-hour rule" in text and "Packaged ERU / RTU / AHU: 16 h per unit" in text


def test_the_tech_hour_rule_is_the_nearest_templates_in_words():
    from estimator.writing.assemble import tech_hour_rule
    from estimator.writing.templates import load_templates
    templates = load_templates()
    rtu = PlannedSystem("RTU", "Rooftop Unit RTU-1 thru 3", "Rooftop Unit", ("RTU-1", "RTU-2", "RTU-3"), 3, "", "",
                        (), (), "", "", "", "")
    assert tech_hour_rule(rtu, templates) == "Packaged ERU / RTU / AHU: 16 h per unit"
    odd = PlannedSystem("ZC", "Zamboni Charger", "Zamboni Charger", (), 1, "", "", (), (), "", "", "", "")
    assert tech_hour_rule(odd, templates) == "none in the template"


# --- round 4, Part B: the questions ---------------------------------------------------------------------------

def test_the_write_prompt_gives_the_controls_contractor_what_no_one_else_is_named_for_on_a_field_ddc_unit():
    for words in ("No named party + field DDC unit → CC furnishes it.", "EXPLICIT ASSIGNMENT ALWAYS WINS.",
                  "No named party + packaged/factory controls unit"):
        assert words in WRITE_PROMPT, words


# --- the reading passes ask through the judge ------------------------------------------------------------

from estimator.writing.judge import READ_PASS


def test_a_pass_is_asked_and_its_answer_cached(tmp_path):
    reply = {"facts": [], "contradictions": [], "confirmations": [], "understanding": "A school."}
    client = FakeClient(_response(reply))
    judge = _judge(tmp_path, client)

    got = judge.ask_pass("the schedules pass", "SYSTEM", "PROMPT", {"type": "object"})
    assert got == (reply, "claude-opus-5-5")
    assert client.calls[0]["system"] == "SYSTEM"
    assert judge.calls == 1
    again = judge.ask_pass("the schedules pass", "SYSTEM", "PROMPT", {"type": "object"})
    assert again == got and judge.cached == 1 and len(client.calls) == 1


def test_an_answer_without_a_facts_list_is_unusable(tmp_path):
    judge = _judge(tmp_path, FakeClient(_response({"understanding": "nothing else"})))
    assert judge.ask_pass("the plans pass", "SYSTEM", "PROMPT", {"type": "object"}) is None
    assert "could not be read" in judge.last_error


def test_in_chat_mode_a_pass_waits_as_a_request_of_its_own_kind(tmp_path):
    judge = Judge(tmp_path / "cache", mode="chat", job="26-9999 Somerville")
    assert judge.ask_pass("the schedules pass", "SYSTEM", "Job: 26-9999 Somerville\nPROMPT", {"type": "object"}) is None
    assert judge.waiting == 1
    request = json.loads(next(judge.requests_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert request["kind"] == READ_PASS and request["system"] == "the schedules pass" and request["job"] == "26-9999 Somerville"


# --- writing from the ledger entry ------------------------------------------------------------------------

from estimator.writing.whole_job import ledger_check, parse_scope, write_prompt, write_schema
from estimator.writing.style import load_house_style


def _ledger_answer(*lines):
    return {"lines": list(lines), "client_notes": [], "review_notes": [], "tech_hours": None,
            "quick_scan": {}, "explanation": "", "contradictions": [], "misc_responsibilities": [],
            "exclusions": [], "qc": []}


def _ledger_line(text, quantity=None, fact_ids=("F1",)):
    return {"text": text, "reference": "each VAV box shall maintain", "flag": "", "flag_text": "", "quantity": quantity,
            "quote": "twelve boxes" if quantity is not None else "", "source_id": "[S2]", "depth": 1,
            "fact_ids": list(fact_ids)}


def test_the_write_prompt_puts_the_ledger_entry_before_the_evidence():
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    text = write_prompt(system, "[S2] evidence", [], [], [], "", ledger_text="F1 family VAV = Variable Air Volume Box [S5] “x” (settled, seed)")
    assert text.index("The job ledger's facts for this system") < text.index("[S2] evidence")
    assert "names, in fact_ids, the ids of the facts it rests on" in text
    assert "fact_ids" in write_schema()["properties"]["lines"]["items"]["required"]


def test_parse_scope_reads_the_fact_ids():
    style = load_house_style()
    scope = parse_scope(_ledger_answer(_ledger_line("Furnish and Install Space Temperature Sensor", fact_ids=["[F1]", "F9", "nonsense"])),
                        "m", style, frozenset({"S2"}))
    assert scope.lines[0].fact_ids == ("F1", "F9")


def test_ledger_check_refuses_lines_naming_no_fact_or_a_count_the_ledger_lacks():
    style = load_house_style()
    scope = parse_scope(_ledger_answer(
        _ledger_line("Furnish and Install Space Temperature Sensor (Qty. 12 Total)", 12),
        _ledger_line("Furnish and Install Discharge Air Temperature Sensor", fact_ids=[]),
        _ledger_line("Furnish and Install VAV Controller", 13)), "m", style, frozenset({"S2"}))
    checked = ledger_check(scope, frozenset({"F1", "F2"}), frozenset({12, 14}))
    assert [line.text for line in checked.lines] == ["Furnish and Install Space Temperature Sensor (Qty. 12 Total)"]
    assert checked.refused[-2:] == (
        "“Furnish and Install Discharge Air Temperature Sensor” names no fact of this system's ledger entry; left out",
        "“Furnish and Install VAV Controller” gives 13, which is no count in this system's ledger entry; left out")
    assert ledger_check(scope, frozenset(), frozenset()) == scope


def test_write_system_carries_the_ledger_entry_and_checks_the_lines(tmp_path):
    reply = _ledger_answer(_ledger_line("Furnish and Install Space Temperature Sensor"),
                          _ledger_line("Furnish and Install VAV Controller", 13))
    client = FakeClient(_response(reply))
    judge = _judge(tmp_path, client)
    system = PlannedSystem(**{k: v for k, v in _system().items()})
    scope = judge.write_system(system, "[S2] evidence", [], [], [], "", ledger_text="F1 family VAV = x [S5] “x” (settled, seed)",
                               facts=("F1",), counts=(12,))
    assert "F1 family VAV" in str(client.calls[0]["messages"][0]["content"])
    assert [line.text for line in scope.lines] == ["Furnish and Install Space Temperature Sensor"]
    assert any("gives 13" in r for r in scope.refused)


def test_ledger_check_refuses_a_count_written_in_the_text_the_ledger_lacks():
    style = load_house_style()
    scope = parse_scope(_ledger_answer(_ledger_line("Furnish and Install VAV Controller (Qty. 13 Total)")),
                        "m", style, frozenset({"S2"}))
    assert scope.lines[0].quantity is None
    checked = ledger_check(scope, frozenset({"F1"}), frozenset({12, 14}))
    assert checked.lines == ()
    assert checked.refused[-1] == ("“Furnish and Install VAV Controller (Qty. 13 Total)” gives 13, which is no count "
                                   "in this system's ledger entry; left out")


def test_ledger_check_keeps_a_ledger_count_written_in_the_text():
    style = load_house_style()
    scope = parse_scope(_ledger_answer(_ledger_line("Furnish and Install VAV Controller (Qty. 12 Total)")),
                        "m", style, frozenset({"S2"}))
    checked = ledger_check(scope, frozenset({"F1"}), frozenset({12, 14}))
    assert [line.text for line in checked.lines] == ["Furnish and Install VAV Controller (Qty. 12 Total)"]
