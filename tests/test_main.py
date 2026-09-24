"""One plain-words message per way the tool can be stopped, instead of a Python traceback."""
import json

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
    """A destination that can't be written to at all (the closest a test can get, cross-platform,
    to "the file is open in Word or Excel") is reported in plain words, not a Python traceback."""
    job_path = tmp_path / "job.json"
    job_path.write_text(small_job.model_dump_json(), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    locked = out / f"{small_job.header.quote_number} Proposal.docx"
    locked.mkdir()    # a directory where the proposal needs to be written: Windows refuses to open it for writing
    code, _, err = _run(["build", str(job_path), "--out", str(out)], capsys)
    assert code == 1
    assert err.strip().endswith("is open in Word or Excel — close it and run again")


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
