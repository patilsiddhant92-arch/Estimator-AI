import shutil
from pathlib import Path

import pytest

from estimator.catalogue import documents
from estimator.catalogue.documents import find_documents, job_name
from pdfs import Page, make_pdf

DRAWING = Page(width=3024, height=2160, texts=((200, 200, "FLOOR PLAN", 20),))
LETTER = Page(texts=((72, 72, "Some words on a page", 12),))


@pytest.fixture
def job(tmp_path):
    root = tmp_path / "26-9999, 1 Test Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Marked_Mech.pdf", DRAWING)
    make_pdf(base / "Marked_15970.pdf", LETTER)
    make_pdf(base / "Project book.pdf", Page(texts=((72, 72, "SECTION 23 09 23 - INSTRUMENTATION AND CONTROL", 12),)))
    make_pdf(base / "Addendum 1.pdf", LETTER)
    make_pdf(base / "RFI Log for WP-4.pdf", LETTER)
    make_pdf(base / "Bid form.pdf", LETTER)
    make_pdf(base / "Specs" / "23-09-00-Controls.pdf", LETTER)
    make_pdf(root / "2. Takeoffs" / "2. A" / "Mech rev A.pdf", DRAWING)
    make_pdf(root / "3. Proposal" / "1. Base Proposal" / "26-9999.pdf", LETTER)
    make_pdf(root / "5. Price Workup" / "sheet.pdf", LETTER)
    make_pdf(base / "26-9998" / "2. Takeoffs" / "their plan.pdf", DRAWING)
    (base / "copies").mkdir()
    shutil.copy(base / "Marked_Mech.pdf", base / "copies" / "Mech again.pdf")
    (base / "broken.pdf").write_bytes(b"this is not a pdf")
    (base / "notes.txt").write_text("not a pdf")
    return root


def _by_name(folder):
    return {d.relative.rsplit("/", 1)[-1]: d for d in folder.documents}


def test_job_name_is_the_number():
    from pathlib import Path
    assert job_name(Path("D:/x/26-0352, Harbor Point, 1 Invented Street")) == "26-0352"
    assert job_name(Path("D:/x/26-0246")) == "26-0246"


def test_each_document_is_found_with_its_kind(job):
    documents = _by_name(find_documents(job))
    kinds = {name: d.kind for name, d in documents.items()}
    assert kinds == {
        "Marked_Mech.pdf": "drawings", "Marked_15970.pdf": "specs", "Project book.pdf": "specs",
        "Addendum 1.pdf": "addendum", "RFI Log for WP-4.pdf": "rfi", "Bid form.pdf": "other",
        "23-09-00-Controls.pdf": "specs", "Mech rev A.pdf": "drawings", "Mech again.pdf": "drawings",
        "broken.pdf": "unreadable",
    }


def test_revision_comes_from_the_folder_under_takeoffs(job):
    documents = _by_name(find_documents(job))
    assert documents["Marked_Mech.pdf"].revision == "base"
    assert documents["23-09-00-Controls.pdf"].revision == "base"
    assert documents["Mech rev A.pdf"].revision == "A"


def test_relative_paths_and_page_counts(job):
    documents = _by_name(find_documents(job))
    assert documents["Marked_Mech.pdf"].relative == "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    assert documents["Marked_Mech.pdf"].pages == 1
    assert documents["broken.pdf"].pages == 0


def test_the_same_file_twice_is_catalogued_once(job):
    documents = _by_name(find_documents(job))
    assert documents["Mech again.pdf"].duplicate_of == "2. Takeoffs/1. Base Takeoff/Marked_Mech.pdf"
    assert documents["Marked_Mech.pdf"].duplicate_of is None


def test_ames_own_folders_and_other_jobs_are_left_out_and_listed(job):
    folder = find_documents(job)
    assert folder.name == "26-9999"
    assert not [d for d in folder.documents if "Proposal" in d.relative or "Price Workup" in d.relative]
    assert not [d for d in folder.documents if "26-9998" in d.relative]
    assert folder.notes == ("26-9998 is another job's folder inside this one — catalogue it on its own",)
    assert folder.left_out == ("3. Proposal", "5. Price Workup")
    assert folder.nested_jobs == ("2. Takeoffs/1. Base Takeoff/26-9998",)


def test_files_that_are_not_pdfs_are_listed_not_dropped(job):
    folder = find_documents(job)
    assert folder.other_files == ("2. Takeoffs/1. Base Takeoff/notes.txt",)


def test_a_date_named_folder_without_its_own_takeoffs_is_not_a_nested_job(tmp_path):
    # I6: "^\d{2}-\d{4}" also matches a date; only a folder with its own Takeoffs/Proposal/
    # Price Workup/Project Documents folder inside is really another job.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "03-2026 Addendum 1" / "Addendum.pdf", LETTER)
    folder = find_documents(root)
    assert folder.nested_jobs == () and folder.notes == ()
    assert any(d.relative.endswith("03-2026 Addendum 1/Addendum.pdf") for d in folder.documents)


def test_a_nested_job_needs_its_own_documents_folder(tmp_path):
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "26-9998" / "2. Takeoffs" / "their plan.pdf", DRAWING)
    make_pdf(base / "26-9997" / "loose file.pdf", LETTER)   # looks like a job number, but no Takeoffs/Proposal inside
    folder = find_documents(root)
    assert folder.nested_jobs == ("2. Takeoffs/1. Base Takeoff/26-9998",)
    assert any(d.relative.endswith("26-9997/loose file.pdf") for d in folder.documents)


def test_electrical_left_out_only_at_the_top_of_the_job(tmp_path):
    # I6: AME's own top-level "Electrical" quote folder is left out; a discipline subfolder of
    # the real bid drawings, several levels down, is not.
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(root / "6. Electrical" / "sub quote.pdf", LETTER)
    make_pdf(base / "Electrical" / "E-101.pdf", DRAWING)
    folder = find_documents(root)
    assert folder.left_out == ("6. Electrical",)
    assert any(d.relative.endswith("Base Takeoff/Electrical/E-101.pdf") for d in folder.documents)


def test_same_size_head_and_tail_but_a_different_middle_are_not_duplicates(tmp_path):
    # I8: size plus the first and last megabyte can match on two different files — a PDF's
    # middle can differ while its size, header objects and tail don't.
    from estimator.catalogue.documents import _find_duplicate
    head, tail = b"H" * (1 << 20), b"T" * (1 << 20)
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(head + b"AAAA" + tail)
    b.write_bytes(head + b"BBBB" + tail)
    seen: dict = {}
    assert _find_duplicate(a, "a.pdf", seen) is None
    assert _find_duplicate(b, "b.pdf", seen) is None


def test_a_genuine_byte_for_byte_copy_is_still_a_duplicate(tmp_path):
    from estimator.catalogue.documents import _find_duplicate
    head, tail = b"H" * (1 << 20), b"T" * (1 << 20)
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(head + b"SAME" + tail)
    b.write_bytes(head + b"SAME" + tail)
    seen: dict = {}
    assert _find_duplicate(a, "a.pdf", seen) is None
    assert _find_duplicate(b, "b.pdf", seen) == "a.pdf"


def test_a_folder_os_walk_cannot_open_is_flagged_not_fatal(tmp_path, monkeypatch):
    root = tmp_path / "26-9999"
    make_pdf(root / "2. Takeoffs" / "1. Base Takeoff" / "spec.pdf", LETTER)
    real_walk = documents.os.walk

    def _walk(top, onerror=None, **kwargs):
        if onerror is not None:
            onerror(OSError(13, "Permission denied", str(Path(top) / "Locked")))
        yield from real_walk(top, onerror=onerror, **kwargs)

    monkeypatch.setattr(documents.os, "walk", _walk)
    folder = find_documents(root)
    assert any("Could not open folder" in n and "Locked" in n for n in folder.notes)
    assert len(folder.documents) == 1


def test_a_password_protected_pdf_is_its_own_kind(tmp_path):
    import pymupdf
    root = tmp_path / "26-9999"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    base.mkdir(parents=True)
    locked = pymupdf.open()
    locked.new_page()
    locked.save(str(base / "Locked.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret")
    [document] = find_documents(root).documents
    assert document.kind == "password" and document.pages == 0


def test_documents_are_listed_in_a_fixed_order(job):
    assert [d.relative for d in find_documents(job).documents] == sorted(d.relative for d in find_documents(job).documents)


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_documents(tmp_path / "nowhere")


@pytest.mark.parametrize("name", ["2. Takeoffs", "Bid set from the owner"])
def test_the_takeoff_folder_as_input_reads_electrical_and_its_revision_folders(tmp_path, name):
    # RD-8: with the takeoff folder itself as the input, its "Electrical" subfolder is a bid document folder (AME's
    # own folders sit only at the top of the job), and a revision folder directly under it is that revision; a
    # discipline folder is no revision.
    root = tmp_path / name
    make_pdf(root / "Electrical" / "E.pdf", DRAWING)
    make_pdf(root / "Rev 1" / "M.pdf", DRAWING)
    make_pdf(root / "Mechanical" / "M2.pdf", LETTER)
    folder = find_documents(root)
    documents = _by_name(folder)
    assert "E.pdf" in documents and folder.left_out == ()
    assert documents["M.pdf"].revision == "Rev 1"
    assert documents["M2.pdf"].revision == "base"
    assert documents["E.pdf"].revision == "base"


def test_a_discipline_folder_under_takeoffs_is_no_revision(tmp_path):
    # RD-8: "2. Takeoffs/Mechanical" is the base set's mechanical drawings, not a revision named "Mechanical".
    root = tmp_path / "26-9999"
    make_pdf(root / "2. Takeoffs" / "Mechanical" / "M.pdf", DRAWING)
    make_pdf(root / "2. Takeoffs" / "2. A" / "M rev.pdf", DRAWING)
    documents = _by_name(find_documents(root))
    assert documents["M.pdf"].revision == "base"
    assert documents["M rev.pdf"].revision == "A"


def test_a_folder_left_out_is_flagged(tmp_path):
    # RD-8: a folder left out of the job is said in the flags, not only on the Documents tab.
    from estimator.catalogue.job import catalogue_job
    root = tmp_path / "26-9999"
    make_pdf(root / "2. Takeoffs" / "1. Base Takeoff" / "M.pdf", LETTER)
    make_pdf(root / "6. Electrical" / "sub quote.pdf", LETTER)
    flags = catalogue_job(root, tmp_path / "cache").flags
    assert any(f.startswith("6. Electrical was left out") for f in flags)


def test_a_document_inside_an_addendum_folder_is_an_addendum(tmp_path):
    # RD-9: an addendum is known by its folder too, not only by its file name.
    root = tmp_path / "Takeoffs"
    make_pdf(root / "Addendum 2" / "M.pdf", LETTER)
    [document] = find_documents(root).documents
    assert document.kind == "addendum"


def test_a_file_that_cannot_be_opened_is_unreadable_not_fatal(tmp_path, monkeypatch):
    # RD-15: a locked file is one unreadable document; cataloguing goes on.
    root = tmp_path / "Takeoffs"
    make_pdf(root / "Locked.pdf", LETTER)

    def _locked(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(documents, "_fingerprint", _locked)
    [document] = find_documents(root).documents
    assert document.kind == "unreadable" and document.pages == 0
