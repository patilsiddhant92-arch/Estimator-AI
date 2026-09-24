from estimator.proposal.read import read_proposal
from estimator.proposal.sections import closing_texts, opening_texts, scope_texts
from estimator.proposal.write import write_proposal
from estimator.scope import FrontEnd


def test_a_written_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    out = write_proposal(small_job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(small_job)


def test_an_extend_existing_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    front_end = FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs", items=small_job.front_end.items)
    job = small_job.model_copy(update={"front_end": front_end})
    out = write_proposal(job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(job)


def test_26_0246_written_out_again_matches_what_was_sent(sent_job, proposal_template, sent_proposal, tmp_path):
    out = write_proposal(sent_job, proposal_template, tmp_path / "26-0246.docx")
    assert scope_texts(out) == scope_texts(sent_proposal)
    assert closing_texts(out) == closing_texts(sent_proposal)
    assert opening_texts(out) == opening_texts(sent_proposal)
    assert read_proposal(out, proposal_template) == sent_job
