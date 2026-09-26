"""The whole-job judge: one pass plans every system from the dossier, then one pass per system
writes its scope. Every test uses a fake client: no test touches the network."""
import base64
import json
from types import SimpleNamespace

from estimator.writing.judge import CHAT_MODEL, Judge, TechHoursHint
from estimator.writing.templates import load_templates
from estimator.writing.whole_job import (PLAN_PROMPT, SPLIT_LIMIT, WRITE_PROMPT, JobPlan, PlannedSystem,
                                         WrittenLine, WrittenScope, checklist_text, split_dossier)

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


def _plan_answer(**overrides):
    answer = {
        "systems": [
            _system(),
            _system(key="EF-1-2", header="Exhaust Fan EF-1, 2", kind="Exhaust Fan", tags=["EF-1", "EF-2"],
                    quantity=None, quantity_source="", quantity_quote="", sequence_sources=["[S3]"],
                    schedule_sources=[], why="The sequence names two fans; no schedule gives the count."),
            _system(key="UH-1", header="Unit Heater UH-1", kind="EUH / CUH / UH", tags=["UH-1"], quantity=4,
                    quantity_source="[S5]", quantity_quote="QUANTITY 4", sequence_sources=[],
                    schedule_sources=["[S5]"],
                    exception="exception to any work with Qty (4) UH-1 - integral thermostat",
                    why="The schedule says they run on integral thermostats."),
        ],
        "front_end": {"mode": "new-system", "existing_name": "", "lines": ["Provide a new BACnet BMS"],
                      "notes": [], "sources": ["[S1]"]},
        "unresolved": ["Are the exhaust fans on the roof or in the gym?"],
    }
    answer.update(overrides)
    return answer


def _response(answer, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(answer))],
        stop_reason=stop_reason, model=model)


class FakeClient:
    """Stands in for anthropic.Anthropic: records each call and hands back the next canned reply."""

    def __init__(self, *replies, stream=False):
        self.calls = []
        self._replies = list(replies) or [_response(_plan_answer())]
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


def _plan(tmp_path, client, images=(), text=DOSSIER, **kwargs):
    return _judge(tmp_path, client, **kwargs).plan_job(text, images, "CHECKLIST TEXT", "STYLE TEXT")


# --- B1: plan_job --------------------------------------------------------------------------------------

def test_the_plan_is_read_into_planned_systems(tmp_path):
    plan = _plan(tmp_path, FakeClient())

    assert isinstance(plan, JobPlan)
    assert plan.model == "claude-opus-5-5"
    rtu, ef, uh = plan.systems
    assert rtu == PlannedSystem(
        key="RTU-1-3", header="Rooftop Unit RTU-1 thru 3", kind="Packaged ERU / RTU / AHU",
        tags=("RTU-1", "RTU-2", "RTU-3"), quantity=3, quantity_source="[S4]",
        quantity_quote="RTU-1 | 5000 CFM ; RTU-2 | 5000 CFM ; RTU-3 | 4000 CFM",
        sequence_sources=("[S2]",), schedule_sources=("[S4]",), group="", alternate="", exception="",
        why="The schedule lists three rooftop units and the sequence runs them.")
    assert ef.quantity is None and ef.quantity_source == ""
    assert uh.exception == "EXCEPTION TO ANY WORK WITH Qty (4) UH-1 - INTEGRAL THERMOSTAT"
    assert plan.front_end == {"mode": "new-system", "existing_name": "", "lines": ["Provide a new BACnet BMS"],
                              "notes": [], "sources": ["[S1]"]}
    assert plan.unresolved == ("Are the exhaust fans on the roof or in the gym?",)


def test_the_request_carries_the_dossier_checklist_style_and_pictures(tmp_path):
    fake = FakeClient()
    _plan(tmp_path, fake, images=_images(tmp_path))

    (call,) = fake.calls
    assert call["model"] == "test-model"
    assert call["system"] == PLAN_PROMPT
    assert "tool_choice" not in call and "temperature" not in call
    fmt = call["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["required"]) == {"systems", "front_end", "unresolved"}
    content = call["messages"][0]["content"]
    text = "\n".join(block["text"] for block in content if block["type"] == "text")
    for part in (DOSSIER.strip(), "CHECKLIST TEXT", "STYLE TEXT", "H601 HVAC SCHEDULES — picture schedule"):
        assert part in text
    (image,) = [block for block in content if block["type"] == "image"]
    assert image["source"] == {"type": "base64", "media_type": "image/png",
                               "data": base64.standard_b64encode(PNG).decode("ascii")}


def test_the_prompt_asks_for_every_system_with_sources_and_no_invented_numbers():
    low = PLAN_PROMPT.lower()
    for words in ("every system", "fire pump", "generator", "heat tracing", "destratification",
                  "quantity column", "never one", "integral thermostat", "alternate", "source id",
                  "never invent"):
        assert words in low


def test_a_streaming_client_is_used_when_it_has_one(tmp_path):
    fake = FakeClient(stream=True)
    plan = _plan(tmp_path, fake)

    assert plan is not None and len(plan.systems) == 3
    assert fake.calls[0]["max_tokens"] >= 32000


def test_a_quantity_with_no_quote_drops_the_system_and_asks_the_estimator(tmp_path):
    answer = _plan_answer()
    answer["systems"][0]["quantity_quote"] = ""
    plan = _plan(tmp_path, FakeClient(_response(answer)))

    assert [s.key for s in plan.systems] == ["EF-1-2", "UH-1"]
    assert plan.dropped and "Rooftop Unit RTU-1 thru 3" in plan.dropped[0]
    assert any("Rooftop Unit RTU-1 thru 3" in question and "3" in question for question in plan.unresolved)


def test_unknown_fields_are_ignored_and_bad_values_cleaned(tmp_path):
    answer = _plan_answer(colour="blue")
    answer["systems"][0].update(extra="ignored", alternate="maybe", header="Qty (3) Rooftop Unit RTU-1 thru 3",
                                tags=["RTU-1", " RTU-1 ", "RTU-2", "RTU-3"])
    answer["systems"][1]["quantity"] = -2
    answer["front_end"]["mode"] = "something else"
    plan = _plan(tmp_path, FakeClient(_response(answer)))

    rtu, ef, _ = plan.systems
    assert rtu.alternate == "" and rtu.header == "Rooftop Unit RTU-1 thru 3"
    assert rtu.tags == ("RTU-1", "RTU-2", "RTU-3")
    assert ef.quantity is None
    assert plan.front_end["mode"] == ""


def test_a_header_the_client_must_not_see_drops_the_system(tmp_path):
    answer = _plan_answer()
    answer["systems"][1]["header"] = "Exhaust Fan EF-1, 2 ($400 each)"
    plan = _plan(tmp_path, FakeClient(_response(answer)))

    assert [s.key for s in plan.systems] == ["RTU-1-3", "UH-1"]
    assert any("Exhaust Fan" in d for d in plan.dropped)


def test_a_header_longer_than_a_block_header_is_kept_for_the_assembly_to_shorten(tmp_path):
    answer = _plan_answer()
    long = "Plumbing Pumps (Domestic Water Pump, HW Circulator, Ejector Pumps, Elevator Sump, Sewage Ejector Pumps)"
    answer["systems"][1]["header"] = long
    plan = _plan(tmp_path, FakeClient(_response(answer)))

    assert plan.systems[1].header == long and plan.dropped == ()


def test_a_cited_source_the_dossier_does_not_have_is_left_out(tmp_path):
    answer = _plan_answer()
    answer["systems"][0]["sequence_sources"] = ["[S2]", "[S999]"]
    plan = _plan(tmp_path, FakeClient(_response(answer)))

    assert plan.systems[0].sequence_sources == ("[S2]",)
    assert any("S999" in question for question in plan.unresolved)


def test_the_same_plan_is_answered_from_the_cache(tmp_path):
    fake = FakeClient()
    judge = _judge(tmp_path, fake)
    first = judge.plan_job(DOSSIER, _images(tmp_path), "CHECKLIST TEXT", "STYLE TEXT")
    second = judge.plan_job(DOSSIER, _images(tmp_path), "CHECKLIST TEXT", "STYLE TEXT")

    assert len(fake.calls) == 1
    assert (judge.calls, judge.cached) == (1, 1)
    assert second == first


def test_a_changed_picture_is_asked_again(tmp_path):
    fake = FakeClient()
    judge = _judge(tmp_path, fake)
    images = _images(tmp_path)
    judge.plan_job(DOSSIER, images, "CHECKLIST TEXT", "STYLE TEXT")
    (tmp_path / "H601.png").write_bytes(PNG + b"changed")
    judge.plan_job(DOSSIER, images, "CHECKLIST TEXT", "STYLE TEXT")

    assert len(fake.calls) == 2


def test_no_key_means_no_plan(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = _judge(tmp_path)
    assert judge.plan_job(DOSSIER, (), "CHECKLIST TEXT", "STYLE TEXT") is None
    assert "no AI key" in judge.last_error


def test_an_unreadable_answer_is_no_plan(tmp_path):
    judge = _judge(tmp_path, FakeClient(_response({"nope": 1})))
    assert judge.plan_job(DOSSIER, (), "CHECKLIST TEXT", "STYLE TEXT") is None
    assert judge.last_error == "the AI answer could not be read"


def test_in_the_chat_the_request_lists_the_pictures_and_the_answer_is_picked_up(tmp_path):
    images = _images(tmp_path)
    judge = _judge(tmp_path, mode="chat")
    assert judge.plan_job(DOSSIER, images, "CHECKLIST TEXT", "STYLE TEXT") is None
    assert judge.waiting == 1

    (request_file,) = judge.requests_dir.glob("*.json")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert request["kind"] == "plan_job"
    assert request["system_prompt"] == PLAN_PROMPT
    assert DOSSIER.strip() in request["prompt"]
    assert "systems" in request["schema"]["properties"]
    assert request["images"] == [{"id": "I1", "path": images[0].path, "what": images[0].what,
                                  "sheet": "H601", "document": "Drawings.pdf", "page": 7}]

    judge.answers_dir.mkdir(parents=True)
    (judge.answers_dir / request_file.name).write_text(json.dumps(_plan_answer()), encoding="utf-8")
    again = _judge(tmp_path, mode="chat")
    plan = again.plan_job(DOSSIER, images, "CHECKLIST TEXT", "STYLE TEXT")
    assert plan is not None and plan.model == CHAT_MODEL
    assert [s.key for s in plan.systems] == ["RTU-1-3", "EF-1-2", "UH-1"]
    assert again.answered_in_chat == 1 and not request_file.exists()


def _huge_dossier():
    sequence = "\n".join(f"[S{n}] {n}. The unit shall run on the BMS schedule and report its alarms. " * 3
                         for n in range(2, 2 + 2000))
    counts = "\n".join(f"[C{n}] EF family: {n} placements on the plans." for n in range(1, 400))
    return (f"1. Job\n[S1] Big job.\n\n2. Sequence of operation\n{sequence}\n\n"
            f"4. Schedules\n[S5000] RTU SCHEDULE: RTU-1 | 5000 CFM\n\n5. Equipment counts\n{counts}\n\n"
            "7. Notes\n[N1] Coordinate with the electrician.\n")


def test_a_huge_dossier_is_split_and_each_part_keeps_the_job_section():
    text = _huge_dossier()
    assert len(text) > SPLIT_LIMIT
    parts = split_dossier(text, SPLIT_LIMIT)

    assert len(parts) >= 2
    assert all(len(part.text) <= SPLIT_LIMIT + 200 for part in parts)
    assert all(part.text.startswith("1. Job") for part in parts)
    assert sum(part.has_schedules for part in parts) == 1
    assert "5. Equipment counts" in parts[-1].text and "2. Sequence of operation" not in parts[-1].text
    assert split_dossier(DOSSIER, SPLIT_LIMIT)[0].text == DOSSIER


def test_a_huge_dossier_asks_in_parts_and_merges_the_plans_by_key(tmp_path):
    first = _plan_answer(unresolved=[])
    second = _plan_answer(systems=[
        _system(tags=["RTU-1", "RTU-2", "RTU-3", "RTU-4"], sequence_sources=["[S12]"], quantity=4,
                quantity_source="[C3]", quantity_quote="4 placements"),
        _system(key="GEN-1", header="Generator", kind="Generator", tags=[], quantity=1, quantity_source="[N1]",
                quantity_quote="one generator", sequence_sources=[], schedule_sources=[], why="The notes."),
    ], unresolved=["Is the generator monitored?"])
    text = _huge_dossier().replace("[N1] Coordinate with the electrician.", "[N1] one generator")
    parts = len(split_dossier(text, SPLIT_LIMIT))
    replies = [_response(first)] + [_response(second)] * (parts - 1)
    fake = FakeClient(*replies)
    images = _images(tmp_path)
    plan = _plan(tmp_path, fake, images=images, text=text)

    assert len(fake.calls) == parts >= 2
    with_images = [c for c in fake.calls if any(b["type"] == "image" for b in c["messages"][0]["content"])]
    assert len(with_images) == 1
    assert [s.key for s in plan.systems] == ["RTU-1-3", "EF-1-2", "UH-1", "GEN-1"]
    rtu = plan.systems[0]
    assert rtu.quantity == 3                                   # the first part's number stands
    assert rtu.tags == ("RTU-1", "RTU-2", "RTU-3", "RTU-4")
    assert rtu.sequence_sources == ("[S2]", "[S12]")
    assert any("in parts" in q for q in plan.unresolved)
    assert any("RTU-1-3" in q and "3" in q and "4" in q for q in plan.unresolved)
    assert "Is the generator monitored?" in plan.unresolved


def test_a_huge_dossier_in_the_chat_writes_one_request_per_part(tmp_path):
    text = _huge_dossier()
    judge = _judge(tmp_path, mode="chat")
    assert judge.plan_job(text, (), "CHECKLIST TEXT", "STYLE TEXT") is None
    requests = [json.loads(p.read_text(encoding="utf-8")) for p in judge.requests_dir.glob("*.json")]
    assert len(requests) == len(split_dossier(text, SPLIT_LIMIT)) >= 2
    assert all(r["kind"] == "plan_job" and "part" in r for r in requests)


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


def test_the_scope_request_carries_the_plan_evidence_checklist_examples_and_style(tmp_path):
    fake = FakeClient(_response(_scope_answer()))
    _write(tmp_path, fake, images=_images(tmp_path))

    (call,) = fake.calls
    assert call["system"] == WRITE_PROMPT
    schema = call["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"lines", "client_notes", "tech_hours", "review_notes"}
    assert "source_id" in schema["properties"]["lines"]["items"]["required"]
    content = call["messages"][0]["content"]
    text = "\n".join(block["text"] for block in content if block["type"] == "text")
    for part in ("Rooftop Unit RTU-1 thru 3", "RTU-1, RTU-2, RTU-3", "[S4]", EVIDENCE.strip(), *OPTIONS,
                 "25-0101", "STYLE TEXT", "H601 HVAC SCHEDULES"):
        assert part in text
    assert "checklist" in text.lower() and "usually present" in text.lower()
    assert [block["type"] for block in content].count("image") == 1


def test_the_write_prompt_treats_the_template_as_a_checklist_and_asks_for_sources():
    low = WRITE_PROMPT.lower()
    for words in ("checklist", "not a closed menu", "source id", "quote", "never work one out", "review_notes"):
        assert words in low


def test_lines_that_break_the_house_style_are_refused(tmp_path):
    answer = _scope_answer()
    answer["lines"] += [_line("Some wiring maybe"), _line("Furnish and Install Sensor (4 tech hours)"),
                        _line("Furnish and Install Filter Switch, CONFIRMED")]
    answer["client_notes"] += ["no stars here", "**$500 allowance"]
    scope = _write(tmp_path, FakeClient(_response(answer)))

    assert [l.text for l in scope.lines] == [OPTIONS[0], OPTIONS[1], "Discharge Air Temperature"]
    assert len(scope.refused) == 5
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

    assert [(l.text, l.depth) for l in scope.lines] == [(OPTIONS[0], 1), ("Filter Alarm", 2)]
    assert any("Discharge Air Temperature Sensor" in r for r in scope.refused)


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

def test_the_plan_prompt_counts_untagged_symbols_keeps_no_info_systems_and_prices_apartment_units_as_adds():
    low = PLAN_PROMPT.lower()
    for words in ("untagged symbols", "no control information", "minimal integration lines",
                  "alternate: \"add\"", "in the hundreds", "the others in why"):
        assert words in low, words


def test_the_write_prompt_asks_for_each_line_once_totals_and_the_house_order():
    assert ("Write each line once. Put point totals as '(Qty. N Total)' when the evidence gives them. Use the house "
            "order: controller, sensors, points, valves and dampers, integration, notes.") in WRITE_PROMPT
    assert "none in the template" in WRITE_PROMPT


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

def test_the_prompts_give_secondary_tagged_equipment_its_own_quantity():
    for prompt in (PLAN_PROMPT, WRITE_PROMPT):
        low = prompt.lower()
        for words in ("secondary tagged equipment", "gravity intake dampers", "jockey pump", "(qty. 2 total)"):
            assert words in low, words


def test_the_write_prompt_gives_ame_the_actuators_controllers_and_sensors_by_default():
    low = WRITE_PROMPT.lower()
    for words in ("no factory controls", "ame furnishes and installs the actuators, ddc controllers and sensors",
                  "unless the documents give them to others", "by the unit manufacturer", "schedule note",
                  "(furnished by others)", "only with a quote that says so"):
        assert words in low, words


def test_the_prompts_write_the_split_system_leak_detection_lines_or_ask():
    for prompt in (PLAN_PROMPT, WRITE_PROMPT):
        low = prompt.lower()
        for words in ("split system", "refrigerant leak detection", "shut-off valve", "chime"):
            assert words in low, words
    assert "otherwise ask" in PLAN_PROMPT.lower() or "unresolved" in PLAN_PROMPT.lower()
    assert "otherwise, ask in review_notes" in WRITE_PROMPT.lower()
