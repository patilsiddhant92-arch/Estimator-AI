# T-001 review (lead, 2026-10-11)

T-001 is accepted. The lead merged `hark/T-001` on branch `lead/t001-review` with these review fixes (commit 03bf985,
4 new tests):

- A fact whose value is None or "" no longer prints "(None)" or "()", and a unit named "None" is no longer cited by
  the word "none" in the job text.
- The count refs of families and lines now count as citations.
- "EF-1" inside "EF-10" is not a citation (test added).

## Follow-up for you: T-001b (small, after T-002 and T-003)

Family and unit facts use the tag prefix as their subject (`estimator/ledger/seed.py` ~:109, :118). So any whole word
"VAV" anywhere in the job cites every VAV fact, and a lost fact can look covered. Make a family or unit fact count as
cited only by a ref with the same source and quote, or by one of its own tags (a range such as "EF-1 thru 3" expanded),
never by the bare prefix. Test first. Branch `hark/T-001b` from `lead/t001-review` once the lead pushes it, or from
`origin/rebuild` with `hark/T-001` merged. The lead connects the gate to the run and the review page.
