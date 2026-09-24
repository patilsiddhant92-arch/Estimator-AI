from conftest import PROPOSAL_TEMPLATE, SENT_PROPOSAL, SENT_WORKUP, TEST_JOB_FILE
from estimator.scope import Job
from estimator.sent import job_from_sent


def _imported():
    return job_from_sent(SENT_PROPOSAL, SENT_WORKUP, PROPOSAL_TEMPLATE)


def test_hours_come_from_the_workup():
    job, _ = _imported()
    assert job.front_end.tech_hours == 140.0
    assert (job.blocks[0].header, job.blocks[0].tech_hours) == ("*Qty (1) BACnet Data Cabinet", 10.0)
    assert job.blocks[1].tech_hours == 25.0


def test_quantities_come_from_the_workup():
    job, _ = _imported()
    assert [i.quantity for i in job.front_end.items] == [1, 1, 1, 1, 1, 1, None, None, None, None, None, None]
    assert [i.quantity for i in job.blocks[0].items] == [1, 1, 1, None, None, None, None, None]
    router_cabinet = job.blocks[1].items
    assert (router_cabinet[0].quantity, router_cabinet[1].quantity) == (5, 7)
    assert router_cabinet[1].text.startswith("Furnish and Install BACnet IP Router")


def test_alternates_get_their_hours_and_quantities():
    job, _ = _imported()
    add, deduct = job.add_alternates[0].blocks[0], job.deduct_alternates[0].blocks[0]
    assert (add.tech_hours, [i.quantity for i in add.items]) == (4.0, [1, 1])
    assert (deduct.tech_hours, [i.quantity for i in deduct.items]) == (4.0, [1, 1, None])


def test_most_lines_match_between_the_proposal_and_the_workup():
    # The exact figure is printed in Step 5. The sent workup was made from an earlier
    # draft of the proposal, so a handful of lines are expected not to match.
    _, report = _imported()
    assert report.matched >= 200


def test_the_committed_test_job_is_what_the_importer_makes():
    assert Job.model_validate_json(TEST_JOB_FILE.read_text(encoding="utf-8")) == _imported()[0]
