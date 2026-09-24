import shutil

import pytest

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
    assert job_name(Path("D:/x/26-0352, Tishman Speyer, 45 Rockefeller")) == "26-0352"
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


def test_documents_are_listed_in_a_fixed_order(job):
    assert [d.relative for d in find_documents(job).documents] == sorted(d.relative for d in find_documents(job).documents)


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_documents(tmp_path / "nowhere")
