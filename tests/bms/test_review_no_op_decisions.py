"""decisions.json entries that change nothing are refused in words (RUN-12)."""
import json
import re

import pytest

from bms import review
from bms.model import Count, Decision, ModelError


def _write(tmp_path, *decisions):
    (tmp_path / "decisions.json").write_text(json.dumps([d.to_dict() for d in decisions]), encoding="utf-8")


@pytest.mark.parametrize("decision, word", [
    (Decision("EF", "change", device_id="EF.d1", reason="x"), "has no device"),
    (Decision("EF", "change", family_name="Fans"), "changes nothing"),
    (Decision("EF", "change", family_name="Fans", reason="  "), "changes nothing"),
    (Decision("", "change", family_name="Fans", count=Count(value=3)), "system_key is empty"),
])
def test_an_entry_that_changes_nothing_is_refused(tmp_path, decision, word):
    _write(tmp_path, Decision("EF", "accept", device_id="EF.d1"), decision)
    with pytest.raises(ModelError, match=re.escape("decisions[1]")) as caught:
        review.load_decisions(tmp_path)
    assert word in str(caught.value)


def test_a_words_only_family_change_is_kept(tmp_path):
    kept = Decision("EF", "change", family_name="Fans", reason="three on the roof")
    _write(tmp_path, kept, Decision("EF", "change", family_name="Fans", count=Count(value=3)))
    assert review.load_decisions(tmp_path)[0] == kept
