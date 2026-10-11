# T-005e addendum: Master Template and GEM v4 findings (lead, 2026-10-11)

The GEM v4 (the writing instructions) is assets/gem/BMS_DDC_GEM_v4.txt. Findings of the lead's check of our 26-0544 proposal:
Sources: `Brain/Master Template.docx`; `assets/gem/BMS_DDC_GEM_v4.txt` (GEM v4, approved 2026-10-03: the writing
instructions).
- Format: heading "Qty (#) <system>", no sub-headings, "OR" lines for alternatives, '*' notes after the scope lines,
  "**" lines are estimator hints, tech-hour line last. GEM: one '*' note per block (GEM ~548); a quantity note goes on
  the device line (GEM ~609). Our blocks carry 2-3 '*' notes.
- Existing-BMS front end (template ~lines 77-104): tie-in header, network control panel, 3-D graphics, training,
  warranty. Ours had none of panel, graphics, training, warranty.
- GEM v4 order of points (GEM ~408-432): 1 controller; 2 sensors; 3 switches; 4 leak detectors; 5 current switches;
  6 interposing relays; 7 damper actuators; 8 fan and pump signals; 9 primary equipment; 10 position feedback;
  11 other outputs; 12 power wiring; 13 fire alarm wires; 14 filter DP switches; 15 airflow stations; 16 valves;
  17 Install and Wire; 18 other Wire; 19 integration group; 20 miscellaneous. A Master Template entry sets the order
  when it has one (GEM ~396-402). Ours broke it in AHU, EF and pumps.
- Valves: always Furnish and Wire (GEM ~228); factory-unit valves are not CC lines (~291, 294).
- Pumps: Start/Stop, Status and VFD Control always (GEM ~348-349); fault and speed only when called. Chilled and hot
  water are separate blocks (template ~371, 611). Ours had no pump VFD Control.
- Factory controllers belong to the unit maker (GEM ~279-288). Shipped-loose devices: GEM ~296-303.
- Exclusions: only sequence items (GEM ~564); ours had 37 mostly generic lines, demolition excluded twice, and
  conflicts (smoke-detector wires scoped and excluded; airflow station scoped and excluded; factory mounting excluded
  but needed). No Miscellaneous section (GEM ~450-468).
- No rule in the sources for off-hours/prevailing wage, demolition plans or FUTURE items: those are the estimator's
  rulings of 2026-10-11 (memory `rulings-2026-10-11-first-run`); propose them as Playbook rules.
