# Decisions and open questions

## Decided (Siddhant)
- 2026-10-09: The schedule tells which systems are in the job. `Brain/Quantity rules.txt` governs quantities.
- 2026-10-09: The schedule quantity prints. Plan or vision counts that differ are flagged as discrepancies, not printed.
- 2026-10-09: VAV scope must follow `Brain/Master Template.docx`, `Brain/BMS_DDC_GEM_v3.2.docx` and `Brain/Quantity rules.txt`.
- 2026-10-09: Fix all bugs first, then wait for review before rerunning jobs. A discussion is planned.
- Nothing is committed to the app code or pushed without explicit approval. This HarkPro log is pushed at regular intervals (approved 2026-10-09).

- 2026-10-09: AME is the mechanical contractor's sub. Any controls item or sensor the documents give to the mechanical contractor is AME's scope. Example: an EF space thermostat "by mechanical contractor" becomes "Furnish and Install Space Thermostat", not an exception. To be coded (the current EXCEPTION printing is wrong for this case).

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
