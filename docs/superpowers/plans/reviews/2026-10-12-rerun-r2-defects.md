# 26-0544 rerun r2: defect causes (architect, 2026-10-12)

Input: `out/26-0544-r2`. Code: `rebuild` 42bc360. Paragraph numbers are python-docx indexes.

## 1. AHU lines under "Qty (10) Control Valve"

**Cause.** In Job.json, the Control Valve family (CV-1 thru 10, count 10) is the second family of the AHU system.
`plan.link_valves` put it there (`plan.py:1544`). The heading is not a group line, because `group_line("Air Handling
Unit")` gives "" (`assets/gem_order.json`). The heading is a stacked family header:
`render._header_families` (`render.py:1030-1034`) removes only damper families. `_system_blocks` then makes one
"Qty (N)" header per family (`render.py:1067-1069`). It puts all lines on the last header and the hours on the first
(`render.py:1085-1087`). So para 27 (AHU) is empty, and para 28 (valves) holds the 24 lines and 6 notes.
rules.md:686 says a valve goes in the block of its unit, never in a valve system of its own.

**Fix.** `_header_families` also removes valve families (`_is_valve(f.name)`, `render.py:804`) when other
families stay. A valve-only block keeps its header.

**Test.** An invented AHU (2 units) with a Control Valve family (4) gives one header, "Qty (2) Air Handling Unit
AHU-1 thru 2", with all lines under it. A valve-only system keeps its own header. Use the pattern of
`test_render.py:479`. **Owner:** HarkPro.

## 2. Off-hours line not red

**Fact.** F210 (spec, settled, 01 14 00 p.182) has this quote: "if no times are specified therein then the work
hours shall be Monday - Friday 6:00 pm - 6:00 am". Key note 1 on M112.00 and M113.00 also says "DURING OFF HOURS".

**Cause.**
1. `labor_conditions` reads only Spec overview rows with status Found (`labor.py:108-112`, called at
   `run.py:783`). The Working hours row is "Ruled out", because the ruled-out word
   `\bno\s+[a-z][^.;]{0,60}?\bshall\s+be\b` (`assets/reading_lists/scope_review.json:12`) matches "no times ... shall
   be".
2. Even if the row were Found, `calls_for_off_hours` (`labor.py:66-77`) would skip the clause. `_NEGATION`
   (`labor.py:61`) matches "no", and `_CLAUSES` does not split at "then". I ran it: the result is False. Without the
   "if no" part, the result is True.
3. Plan notes and ledger facts are never inputs.

So `estimator/proposal/write.py:497` sees no off-hours condition and keeps the template exclusion in black (para
139).

**Fix.** (a) `labor.py` `_CLAUSES`: split also at `\bthen\b`. (b) `scope_review.json:12`: add
`(?<!if )` and do not let the match pass "then". I checked it: it does not match the quote. (c) Later, read the
ledger `note` facts and plan key notes too. That is new scope, so the lead decides.

**Test.** The invented conditional sentence gives True, with hours "6:00 PM to 6:00 AM". The existing overtime-ban
tests stay False (`test_review_t005e.py:112`, `test_t005e_addendum.py:256`). An invented Division 1 page gives a
Found row. **Owner:** HarkPro.

## 3. Smaller items

**(a) "Qty (##)", para 87.** `FCU.d2` has no quantity. The prefix comes from `render.py:697-700`. `_items`
(`render.py:1096-1098`) makes a line red only for future and notice marks, so the line is black. rules.md:219-220
says "flagged to confirm". Fix (the lead rules): an unknown-count line prints red. Test: a device with no quantity
gives a red run. Note: the writer gave no count, but the assumption ties the sensor to the 55 thermostats.
**Owner:** HarkPro.

**(b) "Qty (5)" under 6 chilled water pumps.** This is correct. The sources are the P-1, 3, 5, 7 and 9 Taco starter
rows. P-11 has its own CP-1 relay panel line. This is not a defect.

**(c) Coil bank.** It has no devices, so only the Evidence Package note prints (`render.py:1055-1058`). Its valves
are in ERV-1. It is not a named exception (rules.md:588-592), so do not print an EXCEPTION line. If the estimator
wants to show it, add a short '*' note in the ERV-1 block. **Owner:** the estimator.

**(d) Demolition twice (paras 161 and 175).** Both lines are in the Word template (template paragraphs 77 and 91).
The writer copies the list as it is. `scope_review.json:188-189` already knows that they are the same. GEM v4:564
and rules.md:599-601 say "only items relevant". Fix: the estimator removes one line from the template. Filtering
by relevance is parked. **Owner:** the estimator, then the lead.

**(e) Eight '*' notes over 200 characters.** `_notes` (`render.py:907-923`) calls `short_points`
(`render.py:74-98`). That splits only at ". " and "; ", into "\n- " points in one paragraph. Seven of the eight are
already split, so the long count is for the full paragraph. The first points stay long, because there is no split at
", because", ", as" or ": ". Also, `_reason` (`render.py:414`) prints "because The". Fix: emit each point as its own
`Item` (ruling 14). When a point is over 150 characters, also split at ", because" and at the first ": ". Lowercase
the first word after "because". Test: an invented 260-character assumption gives at least two lines of 150
characters or less, and no word is lost. **Owner:** HarkPro.

**(f) Review.html: 29 questions on 11 cards, 7 on AHU.** `review._questions` (`review.py:96-218`) makes one
question per finding and per flagged device. `review_page` (`review.py:633-651`) makes one card per system. q11 (a
finding on d22 that also names d23) and q25 (the d23 flag) ask the same thing. Fix: one question per family, with
one sub-point per device. Each sub-point keeps its own Accept/Change, because decisions are keyed by device id.
Merge a device flag into a finding that names it. Test: three flagged devices give one question with three
sub-points, and each sub-point saves its own decision. **Owner:** Grok.

## Fix list

1. Valve families print no header (HarkPro).
2. Off-hours: a conditional is not a ban, in `labor.py` and `scope_review.json:12` (HarkPro). The lead decides
   on the ledger and plan input.
3. '*' notes: one line per point, and "because The" (HarkPro).
4. "Qty (##)" in red: the lead rules (HarkPro).
5. Duplicate template exclusion (the estimator).
6. Review: family questions with sub-points (Grok).
7. Coil bank note (the estimator).
