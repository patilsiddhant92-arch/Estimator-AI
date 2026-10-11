# T-001b report

1. Task T-001b, branch hark/T-001b. Base: origin/rebuild at ce07960 with origin/hark/T-001 (40ec916) merged
   (merge d285cb0). `lead/t001-review` (03bf985) is not on GitHub, so the lead's T-001 review fixes were re-done
   here (see 2). Expect a merge conflict in `src/bms/coverage.py` and `tests/bms/test_coverage.py` with 03bf985;
   on conflict, keep this branch's `_cited` and `_value` and drop the duplicate fix from either side. Code commit:
   4ff7fd6 (this report is the commit after it; see the branch tip).

2. Changed
- src/bms/coverage.py: a family or unit fact is cited only by a ref with its source and quote, or by one of its own
  tags, never by the bare prefix (its subject). Own tags: a unit fact's value, brackets dropped and ranges expanded
  ("EF-1 thru 3, EF-7 (roof)" is EF-1, EF-2, EF-3, EF-7); a family fact's are the tags of the unit facts on its
  prefix plus the tags its own quote names that begin with the prefix. A tag equal to the prefix is dropped. A tag
  matches only as a whole tag: "EF-1" is not in "EF-10", "EF-1A", "XEF-1", "EF-1-2" or "EF-1.5". A "TAG thru N"
  written anywhere in the job is expanded too. Device, sequence and front-end facts are unchanged.
  New helpers, kept apart so the merge is easy: `TAGGED_KINDS`, `_count_refs`, `_tags`, `_own_tags`, `_tag_in`,
  `_with_ranges`, `_value`; `_cited` takes the ledger.
- Re-done review fixes (03bf985): an empty or None value prints no "(None)" or "()" (`_value`); a unit valued None
  is not cited by the word "none" (the unit's value is no longer matched as a word); the count refs of families
  and lines (`Count.sources`, `others[].ref`, `added_up.ref`) count as citations (`_count_refs` in `_refs`).
- tests/bms/test_coverage.py: the T-001 question/exception/clarification test now cites "ZZ-1", not the bare "ZZ"
  (the old form is exactly what T-001b forbids). New tests below.

3. Tests added (15): test_an_empty_value_prints_no_empty_brackets,
   test_a_unit_whose_value_is_none_is_not_cited_by_the_word_none, test_the_count_refs_of_a_family_cite_its_fact,
   test_the_count_refs_of_a_line_cite_its_fact, test_a_tag_inside_a_longer_tag_is_not_a_citation,
   test_the_bare_prefix_cites_no_family_or_unit_fact, test_a_family_named_by_the_prefix_does_not_cite_it,
   test_one_of_its_own_tags_cites_a_family_and_a_unit_fact, test_a_range_in_the_fact_is_expanded,
   test_a_range_in_the_job_is_expanded, test_a_unit_value_that_is_only_the_prefix_gives_no_tag,
   test_a_family_with_no_tags_is_cited_by_its_ref_only, test_a_family_takes_the_tags_its_own_quote_names,
   test_a_served_unit_tag_or_heater_cites_its_fact, test_device_and_sequence_facts_still_cite_by_their_subject.
   tests/bms/test_coverage.py: 23 passed.
   Full suite: 7 failed, 4435 passed, 10 skipped (4452). All 7 are in the baseline 12: 4 of the 5 test_ai chat
   tests, test_review_final3 resource code, test_assets project python, test_main open output folder. The sandbox
   restarts long background jobs, so the suite was run as 19 file chunks (`-n 2`, every test file once) instead of
   one command; the counts add up to the full collection.

4. Not done: no wiring into run.py or the review page (the lead's). A family fact with no unit fact and no prefix
   tag in its quote can be cited only by its ref. A unit fact's contradicting values (a later pass's longer range)
   are not counted as its own tags; only its value is. model.py, playbook, interface spec untouched.

5. Questions: should a tag in a unit fact's contradictions (e.g. a plan's "EF-1 thru 4" against the schedule's
   "EF-1 thru 3") also cite it? This branch says no.
