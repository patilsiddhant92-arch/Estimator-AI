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


## Rebase onto lead/wave2 (T-001b-rebase, 2026-10-11)

- Merged origin/lead/wave2 (28a966c) into hark/T-001b. Conflicts only in src/bms/coverage.py and
  tests/bms/test_coverage.py, resolved as follows:
  - coverage.py: kept this branch's `_cited` (family and unit facts cited only by a ref or their own tags) and its
    `expand` import; kept wave2's `_said` and its finding text (no "(None)" or "()"); dropped this branch's `_value`
    as a duplicate; `_count_refs` is None-safe and includes `added_up.ref`; the family count refs are added once.
  - test_coverage.py: kept both sides' tests (no name clash).
- `PYTHONPATH=src pytest tests/bms/test_coverage.py -q`: 27 passed.
- Full suite `PYTHONPATH=src pytest tests -q -n 2` (Python 3.13): 9 failed, 4821 passed, 10 skipped.
  The 9 failures are all in the known baseline of unchanged origin/rebuild (they fail there too):
  5 in tests/bms/test_ai.py (the chat tests), tests/bms/test_review_final3.py::test_a_real_child_failing_with_the_resource_code_is_run_three_times_then_reported,
  tests/test_assets.py::test_running_on_the_project_python, tests/test_main.py::test_the_output_folder_being_a_file_that_is_open_is_plain,
  and the flaky tests/test_revert_audit_review.py::test_a_test_file_saved_with_a_utf8_bom_is_audited.
  No failure is outside the baseline. These are Windows/sandbox-only; on the lead's PC they should pass.
- `pytest tests/bms` alone was not run separately (the sandbox was loaded by five parallel tasks); tests/bms is
  part of the full run above.
