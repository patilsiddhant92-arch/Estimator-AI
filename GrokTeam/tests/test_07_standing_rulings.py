"""The estimator's rulings on a written system (proposed `bms.rulings.apply_rulings`, patch 07, hooked into
`bms.run` after every write and count rewrite). Sources: GrokTeam/discussion.md.

- FINAL R1 (Siddhant Q4 / R11, discussion.md): every VAV gets "Furnish DDC Controller to the Factory for
  Installation", quantity = the VAV count, even when no document names one (the second documented exception to "No
  standard or fallback lines"; the first is Q1). The old provisional "ask a question" R1 is gone.
- PROVISIONAL R6: an actuator with no named furnisher prints as "Wire ... (Furnished by Others)", not a question.
- Standing Q1 (Siddhant, discussion.md 2026-10-09 14:43 IST): VRF communication wiring is AME's by default.
  Q1 and R1 are the two entries of one table, `bms.rulings.DOCUMENTED_DEFAULTS`; each entry carries its own
  override check (a document gives the item to someone else).
- Standing Q2: the VRF central controller is OEM / vendor scope (no AME line); the remote controller is the
  template's programmable thermostat, OEM-furnished, installed and wired by AME.
- Standing Q7: an end switch prints only where a document calls for one.
- Standing Q11: AME furnishes the refrigerant leak detector ("provide", no party named). Read narrowly: an unnamed
  "provide" makes only a control device (sensor, detector, thermostat, switch, transmitter...) AME's, never a
  damper, a louver or equipment.

Every test fails on current src (no `bms.rulings`) and passes with patch 07. Invented job, generic tags."""
import dataclasses

from bms.model import Count, Device, Family, FrontEnd, Header, Job, Ref, System
from bms.playbook import load_playbook
from bms.render import render

PLAYBOOK = load_playbook()
SCHED = Ref("S3", "invented schedule row", "M-501, Invented.pdf page 6")


def _apply(system, evidence=""):
    from bms.rulings import apply_rulings              # proposed (patch 07); imported after the fixture is built
    return apply_rulings(system, evidence, PLAYBOOK)


def _printed(system):
    job = Job("Invented Job", (system,), front_end=FrontEnd(mode="new-system"),
              header=Header(quote_number="Q-0000", reference="Invented Job", mep_engineer="Invented Engineer",
                            based_on=("Invented drawings",), date="2026-10-09"))
    return [it.runs[0].text for b in render(job, PLAYBOOK).scope.blocks for it in b.items if it.kind == "line"]


def _line(key, slot, name, verb="Furnish and Install", parties=("AME", "AME", "AME"), quote="invented row", n=1):
    ref = Ref("S3", quote, "M-501, Invented.pdf page 6")
    return Device(f"{key}.d1", slot, name, verb, *parties, Count(n, (ref,)), (ref,))


def _system(key, name, shape, prefix_tags, n, devices=(), quote="invented schedule row"):
    ref = Ref("S3", quote, "M-501, Invented.pdf page 6")
    return System(key, name, shape, "field", (Family(name, tuple(prefix_tags), Count(n, (ref,))),),
                  devices=tuple(devices))


def _notes(*lines):
    rows = ["== 7. NOTES ==", "--- M-601, Invented.pdf page 9 ---"]
    rows += [f"[N{i}] {text}" for i, text in enumerate(lines, 1)]
    return "\n".join(rows) + "\n"


def _vrf(devices=()):
    return _system("VRF", "VRF System", "VRF System", ("IDU-1", "IDU-2"), 2, devices)


def _vav(devices=()):
    return _system("VAV", "VAV Boxes", "VAV / Fan VAV", ("VAV-1", "VAV-2"), 2, devices)


def _dampers(devices=(), quote="MD-1 MOTORIZED DAMPER"):
    return _system("MD", "Motorized Dampers", "Motorized Dampers", ("MD-1",), 1, devices, quote)


# ---- the documented defaults table (Q1 and final R1, nothing else) ---------------------------------------------

def test_documented_defaults_hold_exactly_q1_and_r1_each_citing_discussion_md():
    """Guard on the table itself: exactly the two documented exceptions to "No standard or fallback lines"."""
    from bms import rulings                            # proposed (patch 07)
    table = rulings.DOCUMENTED_DEFAULTS
    assert sorted((d.shape, d.line) for d in table) == [
        ("VAV / Fan VAV", "Furnish DDC Controller to the Factory for Installation"),
        ("VRF System", "VRF Communication Wiring")]
    for d in table:
        assert d.citation.strip() and "GrokTeam/discussion.md" in d.citation, d
        assert d.qty in ("one per system", "family count") and d.override.pattern, d


# ---- R1 (FINAL, Siddhant Q4 / R11): every VAV gets the factory DDC controller, qty = VAV count -------------------

def _vav3():
    return _system("VAV", "VAV Boxes", "VAV / Fan VAV", ("VAV-1", "VAV-2", "VAV-3"), 3)


def test_r1_a_3_vav_job_with_no_controller_mention_prints_the_line_with_qty_3():
    """FINAL R1 (a); source GrokTeam/discussion.md."""
    vav = _apply(_vav3())
    (line,) = [d for d in vav.devices if d.slot == "controller"]
    assert line.quantity.value == 3 and (line.verb, line.furnished_by) == ("Furnish", "AME")
    job = Job("Invented Job", (vav,), front_end=FrontEnd(mode="new-system"),
              header=Header(quote_number="Q-0000", reference="Invented Job", mep_engineer="Invented Engineer",
                            based_on=("Invented drawings",), date="2026-10-09"))
    items = [(it.runs[0].text, it.quantity) for b in render(job, PLAYBOOK).scope.blocks for it in b.items
             if it.kind == "line"]
    assert ("Furnish DDC Controller to the Factory for Installation", 3) in items, items


def test_r1_negative_documents_giving_the_vav_controls_to_others_print_no_default():
    """FINAL R1 (b): two wordings."""
    for note in ("CONTROLS BY VAV MANUFACTURER", "VAV BOX CONTROLS BY OTHERS"):
        assert not [d for d in _apply(_vav3(), _notes(note)).devices if d.slot == "controller"], note


def test_r1_negative_a_non_vav_system_never_gets_the_vav_controller():
    """FINAL R1 (c)."""
    for system in (_vrf(), _dampers(), _system("EF", "Exhaust Fans", "Exhaust Fan", ("EF-1",), 1),
                   _system("FCU", "Fan Coil Units", "Fan Coil Unit", ("FCU-1",), 1)):
        assert not [d for d in _apply(system).devices if "to the factory" in d.name.lower()], system.key


def test_r1_a_controller_the_writer_already_wrote_is_not_doubled():
    """FINAL R1, negative: one controller line per VAV block."""
    written = _line("VAV", "controller", "DDC Controller to the Factory for Installation", "Furnish",
                    ("AME", "Unit Mfr.", "Unit Mfr."), "VAV-1 THRU VAV-3", n=3)
    vav = _apply(dataclasses.replace(_vav3(), devices=(written,)))
    assert len([d for d in vav.devices if d.slot == "controller"]) == 1


# ---- R6 (PROVISIONAL): an actuator with no named furnisher prints Wire ... (Furnished by Others) ---------------------

def test_r6_documents_silent_print_wire_damper_actuator_furnished_by_others():
    """PROVISIONAL R6 (reverses 6b's earlier "question, no line")."""
    md = _apply(_dampers())
    assert _printed(md) == ["Wire Damper Actuator (Furnished by Others)"]
    (line,) = md.devices
    assert line.quantity.value == 1 and line.refs           # the schedule's count, cited


def test_r6_a_written_actuator_with_no_named_furnisher_becomes_wire_by_others():
    """PROVISIONAL R6: the writer guessed AME; no cited passage names a furnisher."""
    md = _apply(_dampers([_line("MD", "damper_actuator", "Damper Actuator", quote="MD-1 MOTORIZED DAMPER")]))
    (line,) = md.devices
    assert (line.verb, line.furnished_by, line.wired_by) == ("Wire", "Others", "AME")


def test_r6_documents_naming_the_furnisher_are_left_to_the_writer():
    """PROVISIONAL R6, negative partner: a named furnisher is never overwritten, and no default line is added."""
    said = "DAMPER ACTUATORS FURNISHED AND INSTALLED BY CONTROLS CONTRACTOR"
    written = _apply(_dampers([_line("MD", "damper_actuator", "Damper Actuator", quote=said)]))
    assert [(d.verb, d.furnished_by) for d in written.devices] == [("Furnish and Install", "AME")]
    silent_writer = _apply(_dampers(quote="MD-1 MOTORIZED DAMPER"), _notes(f"MD-1 {said}"))
    assert not [d for d in silent_writer.devices if d.furnished_by == "Others"]


# ---- Q1 (standing, discussion.md): VRF communication wiring is AME's by default ----------------------------------

def test_q1_a_vrf_system_gets_ame_vrf_communication_wiring_by_default():
    """Standing ruling Q1, source GrokTeam/discussion.md (2026-10-09, 14:43 IST)."""
    vrf = _apply(_vrf())
    comm = [d for d in vrf.devices if d.slot == "vrf_comm_wiring"]
    assert len(comm) == 1 and (comm[0].furnished_by, comm[0].installed_by, comm[0].wired_by) == ("AME",) * 3
    assert "VRF Communication Wiring" in _printed(vrf)


def test_q1_negative_a_non_vrf_system_never_gets_the_line_by_default():
    """Standing ruling Q1, negative (a)."""
    for system in (_vav(), _dampers(), _system("EF", "Exhaust Fans", "Exhaust Fan", ("EF-1",), 1)):
        assert not [d for d in _apply(system).devices if "communication" in d.name.lower()]


def test_q1_negative_documents_giving_the_comm_wiring_to_someone_else_print_no_ame_default():
    """Standing ruling Q1, negative (b): two wordings."""
    for note in ("CONTROL WIRING BY VRF MANUFACTURER", "VRF COMMUNICATION WIRING BY DIV 26"):
        vrf = _apply(_vrf(), _notes(note))
        assert not [d for d in vrf.devices if d.slot == "vrf_comm_wiring"], note


# ---- Q2 (standing): central controller OEM scope; remote controller = template programmable thermostat -----------

def test_q2_the_vrf_central_controller_prints_no_ame_line():
    """Standing ruling Q2."""
    vrf = _apply(_vrf([_line("VRF", "central_controller", "Central Controller", "Install and Wire",
                             ("Unit Mfr.", "AME", "AME"), "VRF CENTRAL CONTROLLER")]))
    assert not [d for d in vrf.devices if "central" in d.name.lower() or d.slot == "central_controller"]


def test_q2_the_vrf_remote_controller_is_the_programmable_thermostat_oem_furnished_ame_installed_and_wired():
    """Standing ruling Q2."""
    vrf = _apply(_vrf([_line("VRF", "other_device", "Remote Controller", quote="IDU-1, IDU-2 WIRED REMOTE CONTROLLER",
                             n=2)]))
    (tstat,) = [d for d in vrf.devices if d.slot == "thermostat"]
    assert (tstat.verb, tstat.furnished_by, tstat.installed_by, tstat.wired_by) == (
        "Install and Wire", "Unit Mfr.", "AME", "AME")
    assert "Install and Wire Programmable Thermostat (Furnished by Unit Mfr.)" in _printed(vrf)


def test_q2_negative_a_programmable_thermostat_line_already_right_is_unchanged():
    """Standing ruling Q2, negative partner."""
    line = _line("VRF", "thermostat", "Programmable Thermostat", "Install and Wire", ("Unit Mfr.", "AME", "AME"),
                 "T-STAT SUPPLIED BY UNIT MFR.")
    vrf = _apply(_vrf([line]))
    assert [d for d in vrf.devices if d.slot == "thermostat"] == [line]


# ---- Q7 (standing): an end switch only where a document calls for one ---------------------------------------------

def test_q7_a_document_calling_for_an_end_switch_prints_it():
    """Standing ruling Q7, positive."""
    md = _apply(_dampers(quote="MD-1 MOTORIZED DAMPER W/ END SWITCH"))
    assert _printed(md) == ["Wire Damper Actuator w/ End Switch (Furnished by Others)"]


def test_q7_a_written_end_switch_no_document_calls_for_is_taken_off():
    """Standing ruling Q7, negative."""
    md = _apply(_dampers([_line("MD", "damper_actuator", "Damper Actuator w/ End Switch",
                                quote="MD-1 MOTORIZED DAMPER BY OTHERS")]))
    assert [d.name for d in md.devices] == ["Damper Actuator"]


def test_q7_a_written_end_switch_a_cited_document_calls_for_stays():
    """Standing ruling Q7, positive partner of the negative."""
    md = _apply(_dampers([_line("MD", "damper_actuator", "Damper Actuator w/ End Switch",
                                quote="MD-1 ACTUATOR W/ END SWITCH BY OTHERS")]))
    assert [d.name for d in md.devices] == ["Damper Actuator w/ End Switch"]


# ---- Q11 (standing): AME furnishes the leak detector ---------------------------------------------------------------

def _leak(quote):
    line = _line("RLD", "other_device", "Refrigerant Leak Detector", "Install and Wire", ("Others", "AME", "AME"),
                 quote, n=2)
    return System("RLD", "Refrigerant Leak Detectors", "", "field",
                  (Family("Refrigerant Leak Detector", ("RLD-1", "RLD-2"), Count(2, (SCHED,))),), devices=(line,))


def test_q11_provide_with_no_party_makes_the_leak_detector_ame_furnished():
    """Standing ruling Q11."""
    (line,) = _apply(_leak("PROVIDE REFRIGERANT LEAK DETECTOR IN EACH IDU ROOM")).devices
    assert (line.verb, line.furnished_by, line.installed_by, line.wired_by) == ("Furnish and Install",) + ("AME",) * 3


def test_q11_negative_a_leak_detector_the_documents_give_to_another_party_is_unchanged():
    """Standing ruling Q11, negative."""
    system = _leak("REFRIGERANT LEAK DETECTOR FURNISHED BY VRF MANUFACTURER")
    assert _apply(system).devices == system.devices


def _provided(name, quote):
    line = _line("GEN", "other_device", name, "Install and Wire", ("Others", "AME", "AME"), quote)
    return System("GEN", "Invented Equipment", "", "field",
                  (Family("Invented Equipment", ("GEN-1",), Count(1, (SCHED,))),), devices=(line,))


def test_q11_provide_with_no_party_makes_a_sensor_ame_furnished():
    """Standing ruling Q11 (narrow), positive: a control device other than the leak detector."""
    (line,) = _apply(_provided("Space Temperature Sensor", "PROVIDE SPACE TEMPERATURE SENSOR")).devices
    assert (line.verb, line.furnished_by) == ("Furnish and Install", "AME")


def test_q11_negative_provide_motorized_damper_is_never_made_ame_scope():
    """Standing ruling Q11 (narrow), negative: an unnamed "provide" on a damper is not AME's."""
    system = _provided("Motorized Damper", "PROVIDE MOTORIZED DAMPER")
    assert _apply(system).devices == system.devices


def test_q11_negative_provide_louver_is_never_made_ame_scope():
    """Standing ruling Q11 (narrow), negative: an unnamed "provide" on a louver is not AME's."""
    system = _provided("Louver", "PROVIDE LOUVER")
    assert _apply(system).devices == system.devices


def test_q11_negative_provide_equipment_is_never_made_ame_scope():
    """Standing ruling Q11 (narrow), negative: equipment, even one whose name carries a device word."""
    system = _provided("Condensate Pump w/ Float Switch", "PROVIDE CONDENSATE PUMP W/ FLOAT SWITCH")
    assert _apply(system).devices == system.devices
