"""One plain-words message per way the tool can be stopped, instead of a Python traceback."""
import json
import os
from pathlib import Path

import docx
import pytest

import estimator.__main__ as cli
from estimator.__main__ import main
from estimator.scope import Alternate


def _run(args, capsys):
    code = main(args)
    out, err = capsys.readouterr()
    return code, out, err


def test_a_missing_job_file_is_plain(tmp_path, capsys):
    missing = tmp_path / "no-such-job.json"
    code, _, err = _run(["build", str(missing), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.strip() == f"Stopped: can't find {missing}"


def test_a_job_with_missing_fields_is_plain(tmp_path, capsys):
    job_path = tmp_path / "job.json"
    job_path.write_text("{}", encoding="utf-8")
    code, _, err = _run(["build", str(job_path), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.startswith("Stopped: the job file isn't valid:\n")
    assert "https://errors.pydantic.dev" not in err
    assert "header:" in err and "front_end:" in err


def test_invalid_json_in_the_job_file_is_plain(tmp_path, capsys):
    job_path = tmp_path / "job.json"
    job_path.write_text('{"header": {,}}', encoding="utf-8")
    code, _, err = _run(["build", str(job_path), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.strip().startswith("Stopped: the job file isn't valid: line")


def test_a_missing_proposal_for_import_sent_is_plain(tmp_path, sent_workup, proposal_template, capsys):
    missing = tmp_path / "no-such-proposal.docx"
    code, _, err = _run(["import-sent", str(missing), str(sent_workup), "--out", str(tmp_path / "job.json")], capsys)
    assert code == 1
    assert err.strip() == f"Stopped: can't find {missing}"


@pytest.mark.parametrize("make_args", [
    lambda tmp_path, small_job, sent_workup, sent_proposal, proposal_template: (
        ["build", str(_write_job(tmp_path, small_job)), "--out", str(tmp_path / "out"),
         "--template", str(_corrupt(tmp_path, "bad-template.docx"))]),
    lambda tmp_path, small_job, sent_workup, sent_proposal, proposal_template: (
        ["build", str(_write_job(tmp_path, small_job)), "--out", str(tmp_path / "out"),
         "--workup-template", str(_corrupt(tmp_path, "bad-workup.xlsx"))]),
    lambda tmp_path, small_job, sent_workup, sent_proposal, proposal_template: (
        ["import-sent", str(_corrupt(tmp_path, "bad-proposal.docx")), str(sent_workup),
         "--out", str(tmp_path / "job.json")]),
    lambda tmp_path, small_job, sent_workup, sent_proposal, proposal_template: (
        ["import-sent", str(sent_proposal), str(_corrupt(tmp_path, "bad-workup.xlsx")),
         "--out", str(tmp_path / "job.json")]),
], ids=["build-template", "build-workup-template", "import-sent-proposal", "import-sent-workup"])
def test_a_corrupt_office_file_is_plain(small_job, tmp_path, sent_workup, sent_proposal, proposal_template,
                                        capsys, make_args):
    """A file that isn't really a .docx or .xlsx — not just missing, but present and unreadable —
    is reported in one plain line, never a zipfile or python-docx traceback."""
    args = make_args(tmp_path, small_job, sent_workup, sent_proposal, proposal_template)
    code, _, err = _run(args, capsys)
    assert code == 1
    assert err.strip().startswith("Stopped: ")
    assert err.strip().endswith("can't be opened — is it a real Word file?") or \
        err.strip().endswith("can't be opened — is it a real Excel file?")
    assert "Traceback" not in err


def _write_job(tmp_path, job) -> Path:
    job_path = tmp_path / "job.json"
    job_path.write_text(job.model_dump_json(), encoding="utf-8")
    return job_path


def _corrupt(tmp_path, name) -> Path:
    path = tmp_path / name
    path.write_text("not a real Office file", encoding="utf-8")
    return path


def test_a_template_the_tool_does_not_recognise_is_plain(small_job, tmp_path, capsys):
    bad_template = tmp_path / "bad-template.docx"
    docx.Document().save(str(bad_template))    # a blank document: none of the fixed headings are in it
    job_path = tmp_path / "job.json"
    job_path.write_text(small_job.model_dump_json(), encoding="utf-8")
    code, _, err = _run(["build", str(job_path), "--out", str(tmp_path / "out"), "--template", str(bad_template)], capsys)
    assert code == 1
    assert err.startswith("Stopped: the proposal template has changed:")


def test_a_job_needing_too_many_price_sheets_is_plain(small_job, tmp_path, capsys):
    too_many = small_job.model_copy(update={
        "add_alternates": tuple(Alternate(label=f"ALT {i}: x", blocks=small_job.add_alternates[0].blocks)
                                for i in range(1, 11))})
    job_path = tmp_path / "job.json"
    job_path.write_text(too_many.model_dump_json(), encoding="utf-8")
    code, _, err = _run(["build", str(job_path), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.strip() == "Stopped: the job needs 11 price sheets; the template has 10"
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


def test_the_output_folder_being_a_file_that_is_open_is_plain(small_job, tmp_path, capsys):
    """A destination held open (the closest a test can get, cross-platform, to "the file is open
    in Word or Excel") is reported in plain words, naming the real file the estimator has open —
    never a hidden temp or backup name — not a Python traceback."""
    job_path = tmp_path / "job.json"
    job_path.write_text(small_job.model_dump_json(), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    locked = out / f"{small_job.header.quote_number} Proposal.docx"
    locked.write_bytes(b"an old proposal")
    with open(locked, "rb"):    # an open handle blocks the rename, like Word holding the file open
        code, _, err = _run(["build", str(job_path), "--out", str(out)], capsys)
    assert code == 1
    assert err.strip() == f"Stopped: {locked} is open in Word or Excel — close it and run again"


def test_a_locked_price_sheet_leaves_both_old_files_untouched(small_job, tmp_path, capsys, monkeypatch):
    """If the price sheet can't be replaced (open in Excel), the proposal must not be replaced
    either — both files or neither. Build once to get an old proposal and an old price sheet,
    then rebuild with the price sheet's move failing partway through, and check nothing changed:
    no half-swapped pair, and no leftover temp or backup file."""
    job_path = tmp_path / "job.json"
    job_path.write_text(small_job.model_dump_json(), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["build", str(job_path), "--out", str(out)]) == 0
    proposal = out / f"{small_job.header.quote_number} Proposal.docx"
    sheet = out / f"{small_job.header.quote_number} Price Sheet.xlsx"
    old_proposal, old_sheet = proposal.read_bytes(), sheet.read_bytes()

    real_replace = os.replace

    def fail_on_price_sheet(src, dst):
        if "Price Sheet" in str(src) or "Price Sheet" in str(dst):
            raise PermissionError(13, "The process cannot access the file", str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(cli.os, "replace", fail_on_price_sheet)
    code, _, err = _run(["build", str(job_path), "--out", str(out)], capsys)

    assert code == 1
    assert err.strip() == f"Stopped: {sheet} is open in Word or Excel — close it and run again"
    assert proposal.read_bytes() == old_proposal
    assert sheet.read_bytes() == old_sheet
    assert sorted(p.name for p in out.iterdir()) == sorted([proposal.name, sheet.name])


def test_the_price_books_own_value_error_is_plain(small_job, tmp_path, capsys, monkeypatch):
    bad_aliases = tmp_path / "aliases.json"
    bad_aliases.write_text(json.dumps({"aliases": {"some line": "Not A Real Price Book Item"}}), encoding="utf-8")
    monkeypatch.setattr(cli, "ALIASES", bad_aliases)
    job_path = tmp_path / "job.json"
    job_path.write_text(small_job.model_dump_json(), encoding="utf-8")
    code, _, err = _run(["build", str(job_path), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.strip() == ("Stopped: the alias for 'some line' points at 'Not A Real Price Book Item', "
                           "which isn't in the price book")


def test_an_unexpected_error_is_a_plain_stopped_message_not_a_traceback(tmp_path, capsys, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(cli, "catalogue_job", _boom)
    code, _, err = _run(["catalogue", str(tmp_path), "--out", str(tmp_path / "out")], capsys)
    assert code == 1
    assert err.strip() == "Stopped: the disk went away"


def test_the_quote_number_is_sanitised_for_the_file_name(small_job, tmp_path):
    header = small_job.header.model_copy(update={"quote_number": "26/04:7"})
    job = small_job.model_copy(update={"header": header})
    job_path = tmp_path / "job.json"
    job_path.write_text(job.model_dump_json(), encoding="utf-8")
    out = tmp_path / "out"
    code = main(["build", str(job_path), "--out", str(out)])
    assert code == 0
    assert (out / "26-04-7 Proposal.docx").exists()
    assert (out / "26-04-7 Price Sheet.xlsx").exists()
    assert list(out.iterdir()) == sorted(out.iterdir())   # no stray subfolder from the "/"
