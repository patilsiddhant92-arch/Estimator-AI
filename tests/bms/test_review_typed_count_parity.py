"""T-003 review of record (range 8ccd0b3..ce07960): the review page's count box. The page (`parseNumber`) and the
Python side (`review._typed_count`) read one typed text alike, also when it holds a letter that Python's
case-insensitive matching folds onto an ASCII letter and JavaScript's does not (the long s "ſ", the dotless i "ı",
the dotted capital I "İ", the Kelvin sign), and also when it holds a space character that only one of the two calls a
space. Python never raises on such a text. Invented texts only."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bms import review

NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# letters Python's re.IGNORECASE folds onto ASCII (the long s, the dotless i, the dotted capital I, the Kelvin sign)
FOLDED = ["\u017fix", "\u017feven", "f\u0131ve", "f\u0130ve", "n\u0131ne", "\u017fixteen", "5 unit\u017f", "3 p\u0131ece",
          "3 \u0131tems", "5 UNIT\u017f", "\u212a"]
# space characters: JavaScript's \s and trim() take U+00A0, U+2003 and U+FEFF; Python's \s and strip() take U+001C to
# U+001F and U+0085, which JavaScript does not
SPACES = ["5\u00a0units", "5\u2003units", "\ufeff5", "5\ufeff", "5\ufeffunits", "5\x85units", "5\x1cunits", "\x1f5",
          "5\x1f", "\x855", "\u20285 units\u2029", "5 units\u3000"]
SAMPLES = FOLDED + SPACES + ["5 units", "two", "##", "", "6"]


def run_js(tmp_path: Path, body: str):
    script = tmp_path / "h.js"
    script.write_text(review._SCRIPT_CORE + "\n" + body, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize("text", FOLDED)
def test_python_never_raises_on_a_letter_it_folds_onto_ascii(text):
    kind, value = review._typed_count(text)
    assert kind in ("number", "words", "none")


@pytest.mark.parametrize("text", FOLDED)
def test_a_non_ascii_letter_is_no_count_word_and_no_unit_word(text):
    """The page reads "ſix" and "5 unitſ" as words; so does Python."""
    assert review._typed_count(text) == ("words", None)


@NODE
def test_the_page_and_python_agree_on_folded_letters_and_space_characters(tmp_path):
    read = run_js(tmp_path, f"console.log(JSON.stringify({json.dumps(SAMPLES)}.map(parseNumber)));")
    for text, parsed in zip(SAMPLES, read):
        kind, value = review._typed_count(text)
        assert (parsed["kind"], parsed["value"] if parsed["kind"] == "number" else None) == (kind, value), repr(text)


@pytest.mark.parametrize("text, said", [("5\u00a0units", ("number", 5)), ("\ufeff5", ("number", 5)),
                                        ("5\x85units", ("words", None)), ("5\x1cunits", ("words", None)),
                                        ("\x1f5", ("words", None))])
def test_python_takes_the_spaces_the_page_takes_and_no_other(text, said):
    assert review._typed_count(text) == said
