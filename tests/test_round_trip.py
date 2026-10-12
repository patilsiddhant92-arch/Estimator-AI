import docx

from estimator.proposal.read import read_proposal
from estimator.proposal.sections import closing_texts, opening_texts, scope_texts
from estimator.proposal.word import WordLists
from estimator.proposal.write import write_proposal
from estimator.scope import Alternate, FrontEnd
from estimator.text import squash


# T-009 (ruling 22): the proposal prints one demolition exclusion. These jobs have no Demolition Scope block, so the
# general line stays and the template's specific line is gone; everything else is as sent.
SPECIFIC_DEMOLITION = "Any demolition work not specifically mentioned"


def _one_demolition_line(texts):
    return [t for t in texts if t != SPECIFIC_DEMOLITION]


def test_a_written_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    out = write_proposal(small_job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(small_job)


def test_an_extend_existing_job_reads_back_the_same(small_job, proposal_template, tmp_path, without_prices):
    front_end = FrontEnd(mode="extend-existing", existing_system_name="Honeywell WEBs", items=small_job.front_end.items)
    job = small_job.model_copy(update={"front_end": front_end})
    out = write_proposal(job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(job)


def test_two_add_and_two_deduct_alternates_round_trip(small_job, proposal_template, tmp_path, without_prices):
    """M2: a second (and later) ALT label sits behind its own blank line, the same as the
    first — verified by hand for three add alternates; here with two of each kind."""
    second_add = Alternate(label="ALT 2: Controls for EF-4", blocks=small_job.add_alternates[0].blocks)
    deduct = (
        Alternate(label="ALT 1: Deduct EF-5", blocks=small_job.add_alternates[0].blocks),
        Alternate(label="ALT 2: Deduct EF-6", blocks=small_job.add_alternates[0].blocks),
    )
    job = small_job.model_copy(update={
        "add_alternates": small_job.add_alternates + (second_add,),
        "deduct_alternates": deduct,
    })
    out = write_proposal(job, proposal_template, tmp_path / "p.docx")
    assert read_proposal(out, proposal_template) == without_prices(job)

    document = docx.Document(str(out))
    paragraphs = document.paragraphs
    for label in ("ALT 2: Controls for EF-4", "ALT 1: Deduct EF-5", "ALT 2: Deduct EF-6"):
        index = next(i for i, p in enumerate(paragraphs) if squash(p.text) == label)
        assert not paragraphs[index - 1].text.strip()   # a blank line, not the previous alternate's last line
        assert WordLists.written_numbering(paragraphs[index])[0] in (23, 28)   # still its own numbered ALT list


def test_26_0246_written_out_again_matches_what_was_sent(sent_job, proposal_template, sent_proposal, tmp_path):
    out = write_proposal(sent_job, proposal_template, tmp_path / "26-0246.docx")
    assert scope_texts(out) == scope_texts(sent_proposal)
    assert closing_texts(out) == _one_demolition_line(closing_texts(sent_proposal))
    assert opening_texts(out) == opening_texts(sent_proposal)
    assert read_proposal(out, proposal_template) == sent_job
