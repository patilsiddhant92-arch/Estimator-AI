# HarkPro review (2026-10-09, read-only, main @a54ea82)

## What Hark is building
A parallel QC layer beside the app that reads its outputs (Ledger.json, Job.json, Proposal.docx): doctrine library (lines.json 39 families/438 lines, rulings R1-R18, conflicts C1-C36), coverage gate, 4-tab evidence workbook, run-to-run diff, and a critic/writer QC loop (no AI connection; requests answered by hand). Proposed flow and "golden jobs" in HarkPro/critique.md.

## State
- Doctrine validator OK (319 template lines match, 63 price items).
- HarkPro tests: 47 passed, 1 failed (test_coverage.py:46 test_tags_expand_runs; real bug).
- Issues: tag ranges missed (appio.py:50 vs :66 case); _qty takes max of counts, against R1 (appio.py:103-108); valid MC dismissals rejected (coverage.py:45,52); lenient coverage matching (coverage.py:426,447); silent failures (appio.py:172-187); QC proof not independent (progress.md:10,16).
- patches/fix-all-uncommitted.patch (58 files, +3973/-442) edits src/bms, src/estimator and the Playbook; built on 7e27873, not in the repo; does not apply to main; contradicts R2 (prints MC exceptions); rewrites existing tests.

## Red flags
Pushed directly to main without review (AGENTS.md:11-13); commits use the owner's email, no Co-Authored-By; base branches not pushed; rulings.md says rulings outrank AGENTS.md.

## Open decisions for Siddhant
Confirm R1-R11 are his rulings; resolve conflicts R2 vs rules.md:78-84, R1 vs rules.md:160-166, template lines vs AGENTS.md:28-29; Hark's open questions in HarkPro/discussion.md:13-21 (EF thermostat wiring, R14-R18, price book gaps, merge timing).

## Where GrokTeam adds value (no duplication)
Golden-job scoring harness; independent check/rebase of Hark's patch; real-model QC loop; issue reports to Hark.
