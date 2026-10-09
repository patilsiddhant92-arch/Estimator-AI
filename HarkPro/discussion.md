# Decisions and open questions

## Decided (Siddhant)
- 2026-10-09: The schedule tells which systems are in the job. `Brain/Quantity rules.txt` governs quantities.
- 2026-10-09: The schedule quantity prints. Plan or vision counts that differ are flagged as discrepancies, not printed.
- 2026-10-09: VAV scope must follow `Brain/Master Template.docx`, `Brain/BMS_DDC_GEM_v3.2.docx` and `Brain/Quantity rules.txt`.
- 2026-10-09: Fix all bugs first, then wait for review before rerunning jobs. A discussion is planned.
- Nothing is committed to the app code or pushed without explicit approval. This HarkPro log is pushed at regular intervals (approved 2026-10-09).

- 2026-10-09: AME is the mechanical contractor's sub. Any controls item or sensor the documents give to the mechanical contractor is AME's scope. Example: an EF space thermostat "by mechanical contractor" becomes "Furnish and Install Space Thermostat", not an exception. To be coded (the current EXCEPTION printing is wrong for this case).

- 2026-10-09 (Job 4): when AME provides the controls, the control devices on the unit schedule are AME's (R19). Damper actuators are Furnish and Install when the damper shows on the plans, control diagram or sequence, flagged if the schedule disagrees (R20). Every block lists all its end devices (R21). The evidence prints the proof, not ids (R22).

## Open, for the estimator
0. EF thermostat: does AME also wire it to the fan or starter, or furnish and install it only?
1. New-system opening sentence: keep the template's "...to provide Automated Temperature Controls system." or reword it?
2. Fallback exception reason "NO BMS WORK IN THE CONTRACT DOCUMENTS" is Hark's wording, not the template's. Confirm or replace it.
3. "ALTERNATE #n" with no add/deduct: currently planned as an add, with a question raised. OK?
4. Price book gaps DOC-11..14 (unpriced items, OAT $50 vs $100, 16 UIO $1,000 vs $1,100, markup 15% vs 5%, tax NJ vs NY).
5. Clarifications carried on Job 2a: AC ownership/integration, VAV thermostat ownership, BIPO airflow switch ownership, existing BMS vendor.
6. When to merge: hark/evidence-ui (7e27873) and the hark/fix-all patch into main.
7. Proposal clarifications (*Confirm / *Assumed) print as long internal paragraphs under each system. Proposed fix: one short client-facing line per item in the proposal, with the reasoning kept in the Evidence Package.
8. An empty "DEDUCT ALTERNATES: ALT #:" prints when there are none.

## 2026-10-09: controls items by the mechanical contractor, and schedule notes
- AC drip-pan leak detector: change to the Master Template line "Furnish and Install Leak Sensor". The documents only say it is wired to a local A/V alarm panel; no MC furnishing is stated. Integral refrigerant leak detection stays a client note: "**Refrigeration Leak Detection system is coming with the unit per equipment schedule".
- Condensate pump: change to the Master Template line "Tie-in Condensate Pump Float Switch (Furnished by Mfr.)". The schedule note ("PROVIDE FLOAT OPERATED HIGH WATER ALARM...") is a pump-manufacturer note; the detail says "WIRE TO BMS".
- App rules that conflict with the new ruling or with the Master Template (to update after review):
  - playbook/rules.md 78-84: default ownership, MC owns "unit-mounted safeties not assigned to the controls contractor"
  - playbook/rules.md 122-124: "(Furnished by Mechanical Contractor)" for condensate pumps and float switches; the Master Template says "(Furnished by Mfr.)"
  - playbook/rules.md 466-472: named exceptions list INTEGRAL / LINE-VOLTAGE THERMOSTAT; one BMS word in the schedule notes means priced
  - assets/gem/BMS_DDC_GEM_v3.2.txt Q1: "Mechanical Contractor / MC → MC furnishes it"
- Rules that support "schedule notes are mostly for the OEM": rules.md 105-108 (a generic "provide" with no party named is not AME), 248-262 (packaged unit: the manufacturer owns the device unless a schedule/sequence/plan note gives it to the controls contractor; nothing inside the unit is a line). No explicit rule says "schedule notes address the manufacturer".
9. Job 4: 20 estimator questions in the job's question list. The biggest are integrator eligibility, off-hours work, and smoke detector wiring vs the house exclusion.
10. The app's own Evidence Package still prints source ids. Fixing it means changing Claude's code; OK?
