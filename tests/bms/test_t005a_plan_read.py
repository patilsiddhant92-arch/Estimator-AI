"""T-005a, ruling 1 of 2026-10-11: a count stated on a demolition plan ("CUH-A (TYP. OF 4)" on the demolition plan of
a floor) is the previous job's, so the planner's stated-count reading (`bms.plan_read.Reader._stated_on_plans`) leaves
it out; the new-work plans' stated counts still count. Invented data only."""
from __future__ import annotations

from test_plan import L2_DUCT, L3_DUCT, _cuh_job, _sheet_dossier


def test_a_count_stated_on_a_demolition_plan_is_not_counted():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"),
                             ("MD-102", 5, "LEVEL 3 HVAC DEMOLITION PLAN", "CUH-A (TYP. OF 6)"))
    count = _cuh_job(dossier).systems[0].families[0].count
    assert count.highest() == 4                                    # not 10 with the demolition plan's 6
    assert all("MD-102" not in (r.where or "") for r in count.sources)


def test_the_new_work_plans_stated_counts_still_add_up():
    dossier = _sheet_dossier(("M-101", 3, L2_DUCT, "CUH-A (TYP. OF 4)"), ("M-102", 5, L3_DUCT, "CUH-A (TYP. OF 4)"))
    assert _cuh_job(dossier).systems[0].families[0].count.value == 8
