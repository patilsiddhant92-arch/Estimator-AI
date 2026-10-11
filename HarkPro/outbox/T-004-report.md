# T-004 report

1. Task T-004, branch hark/T-004, base origin/rebuild. No code changed. Last commit: see branch tip.
2. Changed: HarkPro/outbox/T-004-report.md only (this file). No job data.

## Answers (general terms)

**1. Method.** Read the schedules and the spec first: they say which systems and units exist. Then read each plan sheet, listing every unit tag and its devices with a quote and sheet ref per item. Counts come from three sources (schedule, plan tags, spec/riser) and are tabulated side by side. Check: a coverage gate compares every scope line to at least one quote; an independent critic reads the evidence against the scope and only asks questions; leftovers go to the estimator. Highest count prints, others go in a "*" note (ruling 2026-10-10).

**2. Demolition and overlap.** Removed units: counted only if the new unit replaces them; they carry no new controls but get a demo/disconnect note. Existing to remain: listed as excluded, no points. Relocated: counted once at the new location. Part plans that overlap (match lines): a tag is counted once by tag, never by occurrence; tags appearing on two parts are de-duplicated and the overlap is noted in evidence.

**3. Blocks.** Control valves sit under the unit they serve (a unit's block holds its valves, actuators, sensors). Pumps are split by service (e.g. chilled vs hot water), one controller per pump group, not per pump. Unit-mounted devices that ship with the unit and are factory-controlled stay with the factory; loose devices are AME-furnished and flagged.

**4. Front end.** One front-end block: server/workstation graphics, network integration, commissioning. If the existing BMS is not Honeywell WEBS, Johnson FX or Niagara Tridium, I do not guess: I print a generic "integrate to existing BMS (make/model to be confirmed)" line, flag it as an estimator question, and price it pending.

**5. Marking.** FUTURE items: printed as separate marked lines, not in the base total. Factory-furnished devices: listed as "by unit mfr., AME connects only", no price. Loose-shipped devices: "furnished loose, installed by AME", priced. Each mark has a quote behind it.

**6. Where src/bms is weaker.**
- Plan-count-first: it counts from plans through the AI/tiles and can print a count the schedule contradicts; mine starts from the schedule and reconciles.
- The old "required" line flags force lines with no evidence; mine prints only with evidence.
- Reviewing is by the same pass that wrote; an independent critic catches more.
- Sheet text cut at about 8k chars, and sequence/point-list sheets not read, so points are missed.
- Empty blocks get an auto "BY MC" exception rather than a question to the estimator.

## Not done
Nothing code-related, by task.

## Questions for the estimator
none
