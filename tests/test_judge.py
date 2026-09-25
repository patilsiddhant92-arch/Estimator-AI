"""The optional AI judge. Every test uses a fake client: no test touches the network."""
import base64
import json
from types import SimpleNamespace

import pytest

from estimator.writing.judge import (DEFAULT_MODEL, Choice, Composition, Judge, Judgement, TechHoursHint,
                                     WrittenLine)

OPTIONS = [
    "Furnish and Install Space Temperature Sensor",
    "Furnish and Install Space Temperature / Humidity / CO2 Sensor",
    "Furnish Fan Enable",
]
RULES = ["sensor_t_h_co2: the sequence mentions CO2 and humidity",
         "Hint: T, T/H, T/H/CO2 information is mostly in the sequence"]
EVIDENCE = ("Sequence, 23 09 93 page 44: Each VAV box shall maintain space temperature and CO2 "
            "from a combination space sensor with humidity.")


def _answer(**overrides):
    answer = {
        "choices": [
            {"line": OPTIONS[0], "include": False, "quantity": None,
             "why": "The sequence calls for a combination sensor instead.", "quote": "",
             "confidence": 0.8},
            {"line": OPTIONS[1], "include": True, "quantity": 12,
             "why": "The sequence asks for CO2 and humidity at the space.",
             "quote": "space temperature and CO2 from a combination space sensor with humidity",
             "confidence": 0.9},
            {"line": OPTIONS[2], "include": False, "quantity": None,
             "why": "no evidence", "quote": "", "confidence": 0.3},
        ],
        "client_notes": ["**Space sensors to be mounted by others"],
    }
    answer.update(overrides)
    return answer


def _response(answer, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(answer))],
        stop_reason=stop_reason, model=model)


class FakeClient:
    """Stands in for anthropic.Anthropic: records each call and hands back a canned reply."""

    def __init__(self, reply=None, error=None):
        self.calls = []
        self._reply = reply if reply is not None else _response(_answer())
        self._error = error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._reply


def _judge(tmp_path, client):
    return Judge(tmp_path / "cache", model="test-model", client=client)


def test_parses_the_answer(tmp_path):
    fake = FakeClient()
    result = _judge(tmp_path, fake).judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert isinstance(result, Judgement)
    assert [c.line for c in result.choices] == OPTIONS
    combo = result.choices[1]
    assert combo == Choice(line=OPTIONS[1], include=True, quantity=12,
                           why="The sequence asks for CO2 and humidity at the space.",
                           quote="space temperature and CO2 from a combination space sensor with humidity",
                           confidence=0.9)
    assert result.client_notes == ("**Space sensors to be mounted by others",)
    assert result.model == "claude-opus-5-5"
    assert result.dropped == ()


def test_the_request_is_plain_words_and_asks_for_structured_json(tmp_path):
    fake = FakeClient()
    _judge(tmp_path, fake).judge("VAV", EVIDENCE, OPTIONS, RULES)

    (call,) = fake.calls
    assert call["model"] == "test-model"
    assert call["max_tokens"] >= 4000
    assert "temperature" not in call  # current models refuse sampling settings
    assert "tool_choice" not in call  # forced tool use is refused by current models
    fmt = call["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    line_schema = fmt["schema"]["properties"]["choices"]["items"]["properties"]["line"]
    assert line_schema["enum"] == OPTIONS
    prompt = call["system"] + "\n" + call["messages"][0]["content"]
    assert "HVAC controls estimator at AME" in prompt
    assert "VAV" in prompt and EVIDENCE in prompt
    for number, option in enumerate(OPTIONS, start=1):
        assert f"{number}. {option}" in prompt
    for rule in RULES:
        assert rule in prompt


def test_an_unknown_line_is_dropped_and_reported(tmp_path):
    answer = _answer()
    answer["choices"].append({"line": "Furnish and Install Duct Smoke Detector", "include": True,
                              "quantity": None, "why": "made up", "quote": "", "confidence": 0.9})
    result = _judge(tmp_path, FakeClient(_response(answer))).judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert [c.line for c in result.choices] == OPTIONS
    assert result.dropped == ("Furnish and Install Duct Smoke Detector",)


def test_no_quote_caps_the_confidence(tmp_path):
    answer = _answer()
    answer["choices"][0]["confidence"] = 0.95  # no quote, yet sure of itself
    result = _judge(tmp_path, FakeClient(_response(answer))).judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert result.choices[0].confidence == 0.5
    assert result.choices[1].confidence == 0.9  # quoted: kept as given


def test_client_notes_always_start_with_the_double_star(tmp_path):
    answer = _answer(client_notes=["Start/Stop via Fire Alarm System", "  ", "**Keep me"])
    result = _judge(tmp_path, FakeClient(_response(answer))).judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert result.client_notes == ("**Start/Stop via Fire Alarm System", "**Keep me")


def test_the_same_question_is_answered_from_the_cache(tmp_path):
    fake = FakeClient()
    judge = _judge(tmp_path, fake)
    first = judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    second = judge.judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert len(fake.calls) == 1
    assert (judge.calls, judge.cached) == (1, 1)     # counted apart, for the run's summary
    assert second == first
    assert list((tmp_path / "cache" / "judge").glob("*.json"))
    assert not list((tmp_path / "cache" / "judge").glob("*.tmp"))

    # A new judge over the same cache folder does not pay again either.
    again = _judge(tmp_path, FakeClient(error=RuntimeError("should not be called")))
    assert again.judge("VAV", EVIDENCE, OPTIONS, RULES) == first


def test_a_different_question_is_not_a_cache_hit(tmp_path):
    fake = FakeClient()
    judge = _judge(tmp_path, fake)
    judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    judge.judge("VAV", EVIDENCE + " More.", OPTIONS, RULES)

    assert len(fake.calls) == 2


def test_no_key_means_not_available_and_no_answer(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = Judge(tmp_path / "cache")

    assert judge.available is False
    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    assert judge.last_error == "judgement pending — no AI key set"


def test_a_key_in_the_environment_makes_it_available(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    assert Judge(tmp_path / "cache").available is True


def test_an_injected_client_makes_it_available(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert _judge(tmp_path, FakeClient()).available is True


def test_an_api_error_gives_none_and_a_plain_reason(tmp_path):
    judge = _judge(tmp_path, FakeClient(error=RuntimeError("boom")))

    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    assert judge.last_error
    assert "boom" in judge.last_error
    assert not list((tmp_path / "cache" / "judge").glob("*.json"))  # failures are never cached


def test_an_sdk_timeout_is_named_in_plain_words(tmp_path):
    import anthropic
    import httpx2

    error = anthropic.APITimeoutError(request=httpx2.Request("POST", "https://example.invalid"))
    judge = _judge(tmp_path, FakeClient(error=error))

    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    assert "too long" in judge.last_error


@pytest.mark.parametrize("reply, words", [
    (_response(_answer(), stop_reason="max_tokens"), "cut off"),
    (_response(_answer(), stop_reason="refusal"), "declined"),
    (SimpleNamespace(content=[SimpleNamespace(type="text", text="not json")],
                     stop_reason="end_turn", model="m"), "could not be read"),
])
def test_an_unusable_reply_gives_none(tmp_path, reply, words):
    judge = _judge(tmp_path, FakeClient(reply))

    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    assert words in judge.last_error


def test_a_good_answer_clears_the_last_error(tmp_path):
    judge = _judge(tmp_path, FakeClient(error=RuntimeError("boom")))
    judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    judge._client = FakeClient()
    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is not None
    assert judge.last_error is None


def test_the_model_is_set_in_one_place(tmp_path, monkeypatch):
    monkeypatch.delenv("ESTIMATOR_MODEL", raising=False)
    assert DEFAULT_MODEL == "claude-opus-5-5"
    assert Judge(tmp_path, client=FakeClient()).model == "claude-opus-5-5"
    monkeypatch.setenv("ESTIMATOR_MODEL", "claude-sonnet-5")
    assert Judge(tmp_path, client=FakeClient()).model == "claude-sonnet-5"
    assert Judge(tmp_path, model="given", client=FakeClient()).model == "given"


def test_a_stated_quantity_must_be_a_whole_count(tmp_path):
    answer = _answer()
    answer["choices"][1]["quantity"] = -3
    result = _judge(tmp_path, FakeClient(_response(answer))).judge("VAV", EVIDENCE, OPTIONS, RULES)

    assert result.choices[1].quantity is None


# --- the chat hand-off: answers come from the chat, not the API --------------------------------------

def _chat(tmp_path):
    return Judge(tmp_path / "cache", mode="chat")


def _requests(tmp_path):
    return sorted((tmp_path / "cache" / "judge-chat" / "requests").glob("*.json"))


def test_the_chat_judge_is_available_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = _chat(tmp_path)
    assert judge.available is True
    assert judge.model == "claude (chat)"
    assert judge.handoff_dir == tmp_path / "cache" / "judge-chat"
    assert Judge(tmp_path / "cache", mode="chat", handoff_dir=tmp_path / "elsewhere").handoff_dir \
        == tmp_path / "elsewhere"


def test_a_chat_miss_writes_a_request_and_waits(tmp_path, monkeypatch):
    monkeypatch.setattr("anthropic.Anthropic", lambda *a, **k: pytest.fail("the chat judge never calls the API"))
    judge = _chat(tmp_path)

    assert judge.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    [request] = _requests(tmp_path)
    data = json.loads(request.read_text(encoding="utf-8"))
    assert data["key"] == request.stem
    assert data["system"] == "VAV"
    assert data["system_prompt"].startswith("You are an HVAC controls estimator at AME")
    assert EVIDENCE in data["prompt"] and "1. " + OPTIONS[0] in data["prompt"]
    assert data["options"] == OPTIONS
    assert data["schema"]["properties"]["choices"]["items"]["properties"]["line"]["enum"] == OPTIONS
    assert judge.waiting == 1 and judge.answered_in_chat == 0
    assert judge.last_error.startswith("judgement pending — waiting for an answer in the chat")
    assert str(tmp_path / "cache" / "judge-chat" / "requests") in judge.last_error
    assert not list(request.parent.glob("*.tmp"))


def test_an_answer_from_the_chat_is_picked_up_cached_and_the_request_removed(tmp_path):
    judge = _chat(tmp_path)
    judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    [request] = _requests(tmp_path)
    answers = tmp_path / "cache" / "judge-chat" / "answers"
    answers.mkdir(parents=True)
    answer = _answer()
    answer["choices"].append({"line": "Furnish a coffee machine", "include": True, "quantity": None,
                              "why": "made up", "quote": "", "confidence": 0.9})
    (answers / request.name).write_text(json.dumps(answer), encoding="utf-8")

    again = _chat(tmp_path)
    result = again.judge("VAV", EVIDENCE, OPTIONS, RULES)
    assert isinstance(result, Judgement)
    assert [c.line for c in result.choices] == OPTIONS
    assert result.dropped == ("Furnish a coffee machine",)
    assert result.model == "claude (chat)"
    assert again.answered_in_chat == 1 and again.waiting == 0 and again.last_error is None
    assert not request.exists()

    # Now it is in the normal cache: the answers file is not needed again.
    (answers / request.name).unlink()
    third = _chat(tmp_path)
    assert third.judge("VAV", EVIDENCE, OPTIONS, RULES) == result
    assert third.cached == 1 and third.waiting == 0
    assert not _requests(tmp_path)


def test_an_answers_file_that_cannot_be_read_rewrites_the_request(tmp_path):
    judge = _chat(tmp_path)
    judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    [request] = _requests(tmp_path)
    answers = tmp_path / "cache" / "judge-chat" / "answers"
    answers.mkdir(parents=True)
    (answers / request.name).write_text("{not json", encoding="utf-8")
    request.unlink()

    again = _chat(tmp_path)
    assert again.judge("VAV", EVIDENCE, OPTIONS, RULES) is None
    assert [r.name for r in _requests(tmp_path)] == [request.name]
    assert "the answer for VAV could not be read" in again.last_error
    assert again.waiting == 1 and again.answered_in_chat == 0
    assert not list((tmp_path / "cache" / "judge").glob("*.json"))    # nothing bad is cached


def test_chat_and_api_answers_are_cached_apart(tmp_path, monkeypatch):
    from estimator.writing.judge import _key, _prompt
    monkeypatch.delenv("ESTIMATOR_MODEL", raising=False)
    prompt = _prompt("VAV", EVIDENCE, OPTIONS, RULES)
    api, chat = Judge(tmp_path, client=FakeClient()), Judge(tmp_path, mode="chat")
    assert _key(api.model, prompt) != _key(chat.model, prompt)

    # An API answer in the cache is not taken as the chat's, so switching judges afresh.
    api.judge("VAV", EVIDENCE, OPTIONS, RULES)
    chat = Judge(tmp_path, mode="chat")
    assert chat.judge("VAV", EVIDENCE, OPTIONS, RULES) is None and chat.waiting == 1


def test_an_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        Judge(tmp_path, mode="maybe")


# --- lines beyond the options -------------------------------------------------------------------------

OCC = {"text": "Furnish and Install Occupancy Sensor", "depth": 1, "quantity": None,
       "why": "The plans show occupancy sensors in every office.", "quote": "OCC", "confidence": 0.8}


def _with_extras(*extras):
    answer = _answer()
    answer["extra_lines"] = list(extras)
    return answer


def test_the_choose_schema_asks_for_extra_lines(tmp_path):
    fake = FakeClient()
    _judge(tmp_path, fake).judge("VAV", EVIDENCE, OPTIONS, RULES)
    schema = fake.calls[0]["output_config"]["format"]["schema"]
    assert "extra_lines" in schema["required"]
    line = schema["properties"]["extra_lines"]["items"]
    assert set(line["required"]) == {"text", "depth", "quantity", "why", "quote", "confidence"}
    assert "Furnish and Install" in fake.calls[0]["messages"][0]["content"]   # the house verbs are offered


def test_an_extra_line_the_evidence_calls_for_is_kept(tmp_path):
    result = _judge(tmp_path, FakeClient(_response(_with_extras(OCC)))).judge("VAV", EVIDENCE, OPTIONS, RULES)
    [extra] = result.extra_lines
    assert extra == WrittenLine("Furnish and Install Occupancy Sensor", 1, None,
                                "The plans show occupancy sensors in every office.", "OCC", 0.8)
    assert result.refused == ()


def test_extra_lines_that_break_the_house_style_are_dropped_and_listed(tmp_path):
    no_verb = {**OCC, "text": "Occupancy Sensor"}
    hours = {**OCC, "text": "Furnish and Install Occupancy Sensor (4 hours)"}
    counted = {**OCC, "text": "Furnish and Install Light Level Sensor", "quantity": 3, "quote": ""}
    unquoted = {**OCC, "text": "Furnish and Install Door Contact", "quote": ""}
    priced = {**OCC, "text": "Furnish and Install Door Switch $85"}
    an_option = {**OCC, "text": OPTIONS[2].upper()}           # already offered: not an extra line
    answer = _with_extras(no_verb, hours, counted, unquoted, priced, an_option, OCC)
    result = _judge(tmp_path, FakeClient(_response(answer))).judge("VAV", EVIDENCE, OPTIONS, RULES)
    assert [e.text for e in result.extra_lines] == ["Furnish and Install Occupancy Sensor"]
    refused = "\n".join(result.refused)
    for text in ("“Occupancy Sensor”", "(4 hours)", "Light Level Sensor", "Door Contact", "Door Switch"):
        assert text in refused, text
    assert OPTIONS[2].upper() not in refused
    assert "verb" in refused and "tech hours" in refused and "quote" in refused


def test_an_answer_with_no_extra_lines_still_reads(tmp_path):
    result = _judge(tmp_path, FakeClient()).judge("VAV", EVIDENCE, OPTIONS, RULES)
    assert result.extra_lines == () and result.refused == ()


# --- writing a system with no template ------------------------------------------------------------------

HEATER_EVIDENCE = ("Schedule rows:\n- [M-601 ELECTRIC DUCT HEATER SCHEDULE] EDH-1 — KW: 5; CONTROL: SCR\n"
                   "Passages from the sequence of operation and points list:\n[23 09 93, page 12]\n"
                   "The duct heater shall modulate by SCR to hold the discharge air temperature.")
EXAMPLES = [{"job": "26-0246", "header": "Qty (1) Electric Duct Heater EDH-502", "prefixes": ["EDH"],
             "kind_words": ["Electric", "Duct", "Heater"],
             "lines": [{"text": "Furnish Electric Heat Enable (DO)", "depth": 1},
                       {"text": "Furnish and Install Discharge Air Temperature Sensor", "depth": 1}],
             "notes": ["*INTERLOCK WITH SUPPLY FAN"]}] * 6


def _compose_answer(**overrides):
    answer = {
        "header": "Qty (4) Electric Duct Heater",
        "lines": [
            {"text": "Furnish Electric Heat SCR Control (AO)", "depth": 1, "quantity": None,
             "why": "The sequence modulates the heater by SCR.", "quote": "modulate by SCR", "confidence": 0.9},
            {"text": "Furnish and Install Discharge Air Temperature Sensor", "depth": 1, "quantity": 1,
             "why": "The sequence holds the discharge air temperature.",
             "quote": "hold the discharge air temperature", "confidence": 0.8},
            {"text": "Discharge Air Temperature Sensor", "depth": 1, "quantity": None,
             "why": "no verb", "quote": "discharge air", "confidence": 0.8},
            {"text": "Furnish and Install Airflow Switch (2 hours)", "depth": 1, "quantity": None,
             "why": "hours", "quote": "duct heater", "confidence": 0.8},
            {"text": "Furnish and Install High Limit Switch", "depth": 2, "quantity": 4,
             "why": "a count with no quote", "quote": "", "confidence": 0.8},
        ],
        "client_notes": ["**Heater furnished with SCR by the unit manufacturer", "Not a note"],
        "tech_hours": {"per": "unit", "hours": 2, "like": "EUH / CUH / UH"},
    }
    answer.update(overrides)
    return answer


def _analogs():
    from estimator.writing.templates import load_templates
    templates = {t.name: t for t in load_templates()}
    return [templates["EUH / CUH / UH"], templates["VAV / Fan VAV"], templates["Air Curtain"],
            templates["Fan Coil Unit"]]


def _compose(judge):
    from estimator.writing.style import load_house_style
    return judge.compose("Electric Duct Heater", HEATER_EVIDENCE, EXAMPLES, load_house_style(), _analogs())


def test_compose_asks_with_the_evidence_the_style_the_analogs_and_the_examples(tmp_path):
    fake = FakeClient(_response(_compose_answer()))
    _compose(_judge(tmp_path, fake))
    (call,) = fake.calls
    prompt = call["messages"][0]["content"]
    assert "Master Template has no entry for this system" in call["system"]
    assert HEATER_EVIDENCE in prompt
    assert "Install and Wire" in prompt and "(Furnished by Unit Mfr.)" in prompt       # the house style
    assert "EUH / CUH / UH" in prompt and "Furnish and Install BACnet Thermostat" in prompt   # an analog's lines
    assert "VAV / Fan VAV" in prompt and "Air Curtain" in prompt
    assert "Fan Coil Unit" not in prompt                          # at most three analogs
    assert prompt.count("Qty (1) Electric Duct Heater EDH-502") == 4   # at most four examples
    assert "Furnish Electric Heat Enable (DO)" in prompt
    schema = call["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"header", "lines", "client_notes", "tech_hours"}
    assert set(schema["properties"]["lines"]["items"]["required"]) == \
        {"text", "depth", "quantity", "why", "quote", "confidence"}


def test_compose_keeps_what_follows_the_house_style_and_lists_the_rest(tmp_path):
    result = _compose(_judge(tmp_path, FakeClient(_response(_compose_answer()))))
    assert isinstance(result, Composition)
    assert result.header == "Electric Duct Heater"               # the count is the writer's
    assert [line.text for line in result.lines] == ["Furnish Electric Heat SCR Control (AO)",
                                                    "Furnish and Install Discharge Air Temperature Sensor"]
    assert result.lines[1].quantity == 1 and result.lines[1].depth == 1
    assert result.client_notes == ("**Heater furnished with SCR by the unit manufacturer",)
    assert result.tech_hours == TechHoursHint("unit", 2.0, "EUH / CUH / UH")
    refused = "\n".join(result.refused)
    for text in ("“Discharge Air Temperature Sensor”", "(2 hours)", "High Limit Switch", "Not a note"):
        assert text in refused, text


def test_a_tech_hours_suggestion_that_cannot_be_read_is_none(tmp_path):
    answer = _compose_answer(tech_hours={"per": "fortnight", "hours": 2, "like": "EUH / CUH / UH"})
    assert _compose(_judge(tmp_path, FakeClient(_response(answer)))).tech_hours is None
    answer = _compose_answer(tech_hours=None)
    assert _compose(_judge(tmp_path / "b", FakeClient(_response(answer)))).tech_hours is None


def test_compose_is_cached_apart_from_choose(tmp_path):
    fake = FakeClient(_response(_compose_answer()))
    judge = _judge(tmp_path, fake)
    first = _compose(judge)
    assert _compose(judge) == first and len(fake.calls) == 1 and judge.cached == 1


def test_compose_without_a_key_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = Judge(tmp_path / "cache")
    assert _compose(judge) is None and judge.last_error == "judgement pending — no AI key set"


def test_chat_requests_say_which_kind_of_question_they_are(tmp_path):
    judge = _chat(tmp_path)
    judge.judge("VAV", EVIDENCE, OPTIONS, RULES)
    assert _compose(judge) is None
    requests = [json.loads(r.read_text(encoding="utf-8")) for r in _requests(tmp_path)]
    kinds = {r["kind"]: r for r in requests}
    assert set(kinds) == {"choose", "compose"} and judge.waiting == 2
    compose = kinds["compose"]
    assert compose["system"] == "Electric Duct Heater"
    assert compose["system_prompt"].startswith("You are an HVAC controls estimator at AME")
    assert HEATER_EVIDENCE in compose["prompt"]
    assert compose["schema"]["properties"]["tech_hours"]
    assert "lines" in compose["schema"]["required"]
    assert compose["analogs"] == ["EUH / CUH / UH", "VAV / Fan VAV", "Air Curtain"]
    assert "extra_lines" in kinds["choose"]["schema"]["required"]


def test_a_compose_answer_from_the_chat_is_picked_up(tmp_path):
    judge = _chat(tmp_path)
    _compose(judge)
    [request] = _requests(tmp_path)
    answers = tmp_path / "cache" / "judge-chat" / "answers"
    answers.mkdir(parents=True)
    (answers / request.name).write_text(json.dumps(_compose_answer()), encoding="utf-8")

    again = _chat(tmp_path)
    result = _compose(again)
    assert isinstance(result, Composition) and result.model == "claude (chat)"
    assert result.header == "Electric Duct Heater" and len(result.lines) == 2
    assert again.answered_in_chat == 1 and not request.exists()
    assert _compose(_chat(tmp_path)) == result                    # cached from now on


def test_a_choose_answer_is_not_read_as_a_compose_answer(tmp_path):
    judge = _chat(tmp_path)
    _compose(judge)
    [request] = _requests(tmp_path)
    answers = tmp_path / "cache" / "judge-chat" / "answers"
    answers.mkdir(parents=True)
    (answers / request.name).write_text(json.dumps(_answer()), encoding="utf-8")
    again = _chat(tmp_path)
    assert _compose(again) is None and "could not be read" in again.last_error


# --- read_schedule: a schedule that is a picture, read by eye (1.1) ---------------------------------------

SCHEDULE_ANSWER = {"schedules": [{"title": "ELECTRIC HEATER SCHEDULE", "headers": ["TAG", "AREA SERVED", "WATTS"],
                                  "rows": [{"cells": ["UH-1", "FIRE PUMP ROOM", "3000"]},
                                           {"cells": ["CUH-1", "VESTIBULE 005", ""]}],
                                  "notes": ["2. PROVIDE MANUFACTURER'S INTEGRAL THERMOSTAT."]}]}


def _png(tmp_path, name="H601-p19-1.png", body=b"\x89PNG\r\n\x1a\n fake picture"):
    path = tmp_path / "schedule-images" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_read_schedule_sends_the_picture_as_an_image_block_and_caches_the_answer(tmp_path):
    fake = FakeClient(reply=_response(SCHEDULE_ANSWER))
    png = _png(tmp_path)
    judge = _judge(tmp_path, fake)
    assert judge.read_schedule(png, "H601", 19, "EXHAUST FAN SCHEDULE") == SCHEDULE_ANSWER
    [call] = fake.calls
    image, text = call["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(image["source"]["data"]) == png.read_bytes()
    assert "H601" in text["text"] and "EXHAUST FAN SCHEDULE" in text["text"]
    assert "exactly as printed" in call["system"] and "Never guess" in call["system"]
    schema = call["output_config"]["format"]["schema"]
    assert schema["required"] == ["schedules"]
    assert schema["properties"]["schedules"]["items"]["required"] == ["title", "headers", "rows", "notes"]
    again = _judge(tmp_path, FakeClient(error=AssertionError("answered from the cache")))
    assert again.read_schedule(png, "H601", 19, "EXHAUST FAN SCHEDULE") == SCHEDULE_ANSWER and again.cached == 1


def test_read_schedule_sends_every_tile_of_a_big_picture(tmp_path):
    fake = FakeClient(reply=_response(SCHEDULE_ANSWER))
    tiles = (_png(tmp_path, "a-t1.png", b"one"), _png(tmp_path, "a-t2.png", b"two"))
    _judge(tmp_path, fake).read_schedule(_png(tmp_path, "a.png"), "H601", 19, "", tiles=tiles)
    content = fake.calls[0]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]


def test_a_changed_picture_is_asked_again(tmp_path):
    fake = FakeClient(reply=_response(SCHEDULE_ANSWER))
    judge = _judge(tmp_path, fake)
    judge.read_schedule(_png(tmp_path, body=b"first"), "H601", 19, "")
    judge.read_schedule(_png(tmp_path, body=b"second"), "H601", 19, "")
    assert len(fake.calls) == 2


def test_read_schedule_in_the_chat_names_the_png_and_picks_up_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr("anthropic.Anthropic", lambda *a, **k: pytest.fail("the chat judge never calls the API"))
    png = _png(tmp_path)
    judge = _chat(tmp_path)
    assert judge.read_schedule(png, "H601", 19, "EXHAUST FAN SCHEDULE") is None and judge.waiting == 1
    [request] = _requests(tmp_path)
    data = json.loads(request.read_text(encoding="utf-8"))
    assert data["kind"] == "read_schedule" and data["image"] == str(png)
    assert (data["sheet"], data["page"], data["title_hint"]) == ("H601", 19, "EXHAUST FAN SCHEDULE")
    assert data["schema"]["required"] == ["schedules"]
    answers = tmp_path / "cache" / "judge-chat" / "answers"
    answers.mkdir(parents=True)
    (answers / request.name).write_text(json.dumps(SCHEDULE_ANSWER), encoding="utf-8")
    again = _chat(tmp_path)
    assert again.read_schedule(png, "H601", 19, "EXHAUST FAN SCHEDULE") == SCHEDULE_ANSWER
    assert again.answered_in_chat == 1 and not request.exists()


def test_read_schedule_with_no_key_gives_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = Judge(tmp_path / "cache", model="test-model")
    assert judge.read_schedule(_png(tmp_path), "H601", 19, "") is None
    assert judge.last_error == "judgement pending — no AI key set"