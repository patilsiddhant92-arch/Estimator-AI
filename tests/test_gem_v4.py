"""The GEM in plain language: same method, no emoji, the practice rules folded in, the tool's anchors kept."""
import re

from estimator.writing.whole_job import GEM_END, GEM_FILE, GEM_START, gem_prompt

EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿■-◿◆◊️]")
HEADINGS = ["WHO YOU ARE", "STEP 0 — PROJECT QUICK SCAN", "CONTRACTOR NAME RULE",
            "INPUT HANDLING — SEQUENCE AND POINT LIST", "SCOPE OWNERSHIP — PRIMARY RULE",
            "DEVICE OWNERSHIP RESOLUTION", "BLANKET WIRING CLAUSE", "DAMPER ACTUATOR RULE",
            "FEEDBACK SIGNALS — HARDWIRED FURNISH POINTS", "VERB RULES", "FIRE ALARM AND LIFE SAFETY INTERFACE",
            "PACKAGED UNITS — FACTORY CONTROLS", "MANDATORY MINIMUM POINTS", "SOW ORDER — STANDARD TEMPLATE",
            "INTEGRATION LINES — FIXED GROUP", "MISCELLANEOUS RESPONSIBILITIES", "CONTRADICTION AND ASSUMPTION SCAN",
            "SELF-QC", "FLAGS", "ADDITIONAL RULES — NAMING, SENSORS, FILTERS, CONSOLIDATION", "SYSTEM EXPLANATION",
            "END OF INSTRUCTIONS"]


def test_the_tool_loads_v4():
    assert GEM_FILE.name == "BMS_DDC_GEM_v4.txt" and GEM_FILE.exists()


def test_v4_has_no_emoji_or_marks():
    text = GEM_FILE.read_text(encoding="utf-8")
    assert not EMOJI.search(text), EMOJI.search(text).group(0)
    assert "[?]" not in text and "★" not in text and "◊" not in text


def test_v4_keeps_the_headings_in_order():
    text = GEM_FILE.read_text(encoding="utf-8")
    positions = [text.find(h) for h in HEADINGS]
    assert all(p >= 0 for p in positions), [h for h, p in zip(HEADINGS, positions) if p < 0]
    assert positions == sorted(positions)


def test_v4_flags_are_words():
    text = GEM_FILE.read_text(encoding="utf-8")
    for word in ("CONFIRM QUANTITY", "CONFIRM OWNERSHIP", "ASSUMED", "NOTE"):
        assert word in text


def test_v4_folds_in_the_estimators_rules():
    text = GEM_FILE.read_text(encoding="utf-8").lower()
    for phrase in ("install and wire", "furnished by unit mfr.", "never a line per monitored point",
                   "quantity per plumbing drawings", "one \"*\" clarification per block", "uukl",
                   "under the fan", "interlock"):
        assert phrase in text, phrase


def test_the_prompt_still_starts_and_ends_at_the_anchors_and_carries_the_output_section():
    prompt = gem_prompt()
    assert prompt.startswith(GEM_START)
    assert prompt.rstrip().endswith(GEM_END)
    assert "OUTPUT" in prompt and '"red" for CONFIRM QUANTITY' in prompt
    assert "CONNECTING THE DOTS" in prompt and "AME PRACTICE" in prompt


def test_the_assembled_prompt_has_no_glyph_or_arrow():
    prompt = gem_prompt()
    found = EMOJI.search(prompt)
    assert not found, prompt[max(0, found.start() - 60):found.end()]
    assert "→" not in prompt
    assert "flag CONFIRM QUANTITY and write" in prompt          # the connecting section's quantity flag, in words


def test_the_rep_line_without_its_diamond_is_the_house_line_one_level_in():
    from estimator.writing.style import load_house_style
    from estimator.writing.whole_job import parse_scope
    line = {"reference": "the unit has factory controls", "flag": "", "flag_text": "", "quantity": None,
            "quote": "", "source_id": ""}
    answer = {"lines": [dict(line, text="Map Available Points Via Mfr. Provided BMS Interface", depth=1),
                        dict(line, text="Controls Contractor requires mfr. rep to assist in integration, cost to be "
                                        "incurred by mech contractor", depth=1)]}
    scope = parse_scope(answer, "m", load_house_style())
    assert [(written.text, written.depth) for written in scope.lines][-1] == (
        "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor", 2)
