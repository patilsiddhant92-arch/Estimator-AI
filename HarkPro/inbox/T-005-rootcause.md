# T-005 root causes found by the lead (2026-10-11): use them in T-005a, b, c

Traced on the 26-0544 run (code at lead/wave2 0e78113).

## T-005a: AHU 21, EF 10
- AHU 21 = AHU-1..5 counted once in each of four plan groups (M114.00, M214.00, M314.00, M315.00 -> 5 x 4 = 20) plus
  AHU-6 from MD 315.00 (a demolition sheet). Source: dossier counts line "plan placements 21"
  (estimator/writing/dossier.py:953-955, 1184-1187); counts.py cross-check C1 also 21 (bms/counts.py:603-621).
- Only M114.00 and M214.00 merge (estimator/reading/inventory.py:434-494). M314.00 and M315.00 both show AHU-1..5 but
  read as floors 1 and 2 (inventory.py:434-443), so they add.
- Demolition sheets (MD 110.00..114.00, MD 214.00, MD 315.00) are typed "Demolition" and "Plans", and only Schedules
  are filtered out (inventory.py:689-693; bms/counts.py:286-288). So demolition plans are counted.
- EF 10: M114.00+M214.00 once, M314.00 once: 5 per tag x 2. Picture count 6 includes EF-6, seen only on MD sheets.
- The root rule the estimator gave (ruling 2) and your T-004 answer agree: a numbered unit tag (AHU-1, EF-3) is ONE
  unit in the whole job, however many sheets show it: count distinct unit tags, never placements. Placements count
  only for a TYPE tag placed per location (FCU-1 shown 55 times with one schedule row is 55 units: keep that).
  Then leave demolition sheets out (ruling 1). Expected result by the rules: AHU 5, EF 5 (EF-6 demolition only),
  FCU 55, ERV 1, thermostats from new-work sheets only.
- Also: the count_tags answer for M315.00 gave 0 AHU tags where the text layer locates 5.

## T-005b: repeated review questions
- 48 question cards (bms/review.py:290). AHU: one family card (review.py:167-168) plus 22 device cards (review.py:179-180)
  each repeating the count 21 (others 10, 5, 6, 6). counts.py:173-179 flags every device counted from the family, so
  each device gets a card (review.py:171). review.py:101-106 merges only cards with the same system and device id;
  plan.py:1666-1669 removes identical strings only. Also duplicate pairs q36=q47, q37=q48 (ERV, P).
- Fix: a count question is asked once per family; device cards that only repeat the family count are folded into it.

## T-005c: header
- Quote = text before the first comma of the TAKEOFF folder name, else the whole name; Reference = text after the
  comma, else "[project name]" (estimator/writing/front_end.py:370-375; assets/front_end.json:129). Flow: run.py:492,
  510 -> bms/render.py:118 -> estimator/proposal/write.py:95-96. The job folder two levels up is
  "<job number>, <project name>", which front_end.py:371 already parses: read that folder instead.
