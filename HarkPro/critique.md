# Estimator-AI: honest critique and a faster, more accurate flow

## What is strong
- Every printed line traces to a cited fact. That is the right foundation for estimator trust.
- Pricing, rendering and the house templates are deterministic. Good: AI should never do arithmetic or layout.
- The Playbook holds real estimating judgement (packaged vs field DDC, ownership, integration lines).

## What holds it back
1. **Code second-guesses the AI.** Regex and heuristic text parsing decide systems and counts, then the AI writes inside those decisions, and the planner reverts AI corrections. Most bugs this week (VAV 30, 1,763 "boilers", diffusers as systems) came from code guessing at a drawing.
2. **Facts are read, then lost.** On Job 2a the ledger had the RAM/local alarm, every damper, the radiator interlock, the 19 occupancy sensors and the Lutron integration. None printed. Nothing checks that each controls fact ends somewhere.
3. **Too many sources of doctrine.** Master Template, GEM v3.2/v4, rules.md, shapes.json, wording.json, ESTIMATOR_DOCTRINE, Quantity rules and AGENTS. The audit found 38 contradictions. The AI obeys whichever text it read last.
4. **The writer sees one system at a time.** The radiator interlock lives on the VAV, the Lutron integration on the front end, the occupancy sensors on the lighting plan. Per-system context misses cross-system scope.
5. **Tests don't measure the bid.** 3,900 unit tests pass while the proposal is wrong. There is no answer key.
6. **Slow, serial AI steps.** Read passes run one at a time, and counting uses image tiles where the PDF text layer already holds most tags.
7. **Evidence Package: 22 tabs.** Citations / Job ledger / Notes / Spec overview, Equipment / Equipment tags / Schedules, Pages / Sheets / Documents, and Findings / Flags / Bid check repeat each other.

## Proposed flow
1. **Index** (code): split sheets, read the text layer, hash each sheet for caching.
2. **Extract, per sheet, in parallel** (AI): schedule rows with their notes, keynotes, ownership statements, device symbols and counts with locations, each with a citation. Vision only where the text layer is empty.
3. **Reconcile** (code): dedupe same-floor plans, take the schedule count as printed, flag every other count. No scope decisions here.
4. **Scope, per system, with the whole job's facts** (AI): pick lines only from a machine-readable Master Template line library, and apply one rulings file (e.g. "controls by MC are AME's").
5. **Coverage gate** (code): every controls-relevant fact must end as a line, an exception, a clarification, or a dismissal with a reason. An unaccounted fact blocks the proposal.
6. **QC** (independent AI) against an estimator checklist, then **price and render** (code).
7. **Estimator review**: one screen of decisions, whose answers go back into the rulings file.

## The single biggest lever
Golden jobs: the estimator's own final proposals for 3-5 past bids as answer keys, with a score per line (missed, extra, wrong qty, wrong verb). Run them on every change. That turns "it worked in Claude" into a number.

## One source of doctrine
- The Master Template becomes `lines.json`: system → allowed lines, verbs, tech hours and when each line applies.
- `rulings.md` holds the estimator's decisions, dated. It wins over everything.
- GEM and rules.md are retired into those two files.

## Evidence Package, 22 tabs → 4
1. **Summary**: base and alternates, hours, PRICE PENDING, and the decisions needed.
2. **Scope**: one row per printed line, with qty, verb, owner, hours, price and source sheet.
3. **Questions & flags**: one list (findings, flags, bid check, discrepancies), with severity.
4. **Sources**: one citation table (sheet, page, quote).
Raw ledger, sheets and pages go to a hidden or separate debug workbook.

## How Hark Pro helps
- Run sheet extraction and per-system scope as parallel agents (minutes, not an hour).
- Re-run the golden jobs after every fix and post the score to HarkPro.
- Keep the rulings file current from your review answers, so a decision is made once.
