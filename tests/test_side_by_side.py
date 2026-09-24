import importlib.util
from pathlib import Path

from PIL import Image

_spec = importlib.util.spec_from_file_location("side_by_side", Path(__file__).resolve().parents[1] / "tools" / "side_by_side.py")
side_by_side = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(side_by_side)


def test_apostrophes_in_a_path_are_doubled_for_powershell():
    path = Path("D:/Àpps/Estimator AI/tests/data/O'Brien's Building/26-0246.docx")
    quoted = side_by_side._ps_path(path)
    assert "''" not in str(path)   # the source path has single apostrophes, not doubled ones
    assert quoted == str(path).replace("'", "''")
    # embedded, single-quoted, in a PowerShell string literal, every apostrophe must be doubled
    assert quoted.count("''") == str(path).count("'")


def test_compose_puts_two_pages_side_by_side(tmp_path):
    Image.new("RGB", (100, 140), "red").save(tmp_path / "a.png")
    Image.new("RGB", (100, 120), "blue").save(tmp_path / "b.png")
    out = side_by_side.compose(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "ab.png")
    image = Image.open(out)
    assert image.size == (220, 140)
    assert image.getpixel((10, 10)) == (255, 0, 0)
    assert image.getpixel((130, 10)) == (0, 0, 255)
    assert image.getpixel((110, 10)) == (255, 255, 255)
