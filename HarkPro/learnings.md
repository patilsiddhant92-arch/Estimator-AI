# Learnings (what the estimator taught us, and what the runs showed)

Kept short and general so it applies to any job. Rulings with ids are in `doctrine/rulings.md`.

## Scope doctrine (estimator)
1. **We provide the controls, so the control devices are ours.** If AME furnishes the controller, including a controller sent to the unit manufacturer for factory install, the control devices on the unit schedule are AME's. That means sensors, freezestat, drain pan level sensor and filter switch. Print "Furnish and Install", or furnish to the factory and wire. Never print "Install and Wire ... (Furnished by Unit Mfr.)" by default. When unsure, keep it as AME's and flag it. (R19)
2. **Damper actuators are Furnish and Install.** If a damper is on the plans, the control diagram or the sequence, AME furnishes and installs its actuator, even when the schedule lists it with the unit. Add a *Confirm flag when the schedule disagrees. "Wire Damper Actuator" is rare. (R20)
3. **A block lists every end device.** A system is never "Interlock with ..." only. If its points sit on another unit's controller, list the devices in its own block and add a note saying where the points land. (R21)
4. **At least flag it.** A doubtful ownership is never silently given to someone else. Keep it as AME's scope with a *Confirm, or raise it as a question.
5. Earlier, still in force: the schedule count prints and other counts are flagged (R1). A controls item "by MC" is AME's, never an exception (R2). Leak sensor, local RAM and condensate float use the Master Template wording. Count every damper actuator.

## Evidence (estimator)
6. **Show the proof, not ids.** Every scope line shows where the documents say it, word for word: sheet, page, quote. The estimator should never have to follow source ids or line ids. (R22; done in `harkpro/evidence.py`)

## Comparing against another AI's proposal (Job 4)
7. Neither proposal is an answer key. Check each difference against the documents. On Job 4, the other AI was right on the pump controller, the changeover aquastat, and the "valves furnished by AME, installed by MC" note. Hark was right on demolition, the in-unit AHU devices, and not naming a controller brand the spec forbids. Both were wrong on the unit-furnished AHU devices.
8. Read the general notes sheet and the equipment spec sections, not only the controls spec. On Job 4, the general note "controls contractor shall furnish and install all ... devices" and an ERV spec line saying the control center is furnished by the controls contractor both changed ownership. The schedule notes alone pointed the other way.

## Process
9. When the user says stop, stop before the next action and report that nothing changed. A later message may add the full correction list; apply it then.
10. Never modify the app (Claude's code) or push to main. All new work goes in `HarkPro/` on `hark/harkpro`. Job edits are made in Job.json and re-rendered with the app's own renderer.
11. A subagent editing shared scripts can break other jobs. Check `git diff` or the file after delegated work, and revert anything outside the job.
12. QC run by the same agent that wrote the scope is not independent. Say so in the report.
13. The sandbox may lack LibreOffice and `formulas`, so price-sheet totals can't be computed there. Say so; don't guess totals.
