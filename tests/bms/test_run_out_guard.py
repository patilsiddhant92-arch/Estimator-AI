"""Job files must never be written into the app's own folder (the git tree): `estimate` refuses an output or cache
folder inside the repository, except under out/, before it writes anything."""
import pytest

from bms import run
from bms.run import estimate

ROOT = run.ROOT


def test_out_inside_repo_is_refused_and_nothing_is_made(tmp_path):
    target = ROOT / "docs" / "tmpx"
    assert not target.exists()
    try:
        with pytest.raises(ValueError, match="inside the app's folder"):
            estimate(tmp_path / "job", target, tmp_path / "cache")
        assert not target.exists()
    finally:
        if target.exists():
            import shutil
            shutil.rmtree(target)


def test_cache_inside_repo_is_refused(tmp_path):
    target = ROOT / "docs" / "tmpc"
    try:
        with pytest.raises(ValueError, match="inside the app's folder"):
            estimate(tmp_path / "job", tmp_path / "out", target)
        assert not target.exists()
        assert not (tmp_path / "out").exists()
    finally:
        if target.exists():
            import shutil
            shutil.rmtree(target)


def test_folders_outside_the_repo_and_under_out_are_accepted(tmp_path):
    run._check_folders_outside_repo(tmp_path / "out", tmp_path / "cache")
    run._check_folders_outside_repo(ROOT / "out" / "a", ROOT / "out" / "a" / ".cache")


def test_dotdot_cannot_sneak_into_the_repo(tmp_path):
    with pytest.raises(ValueError):
        run._check_folders_outside_repo(ROOT / "out" / ".." / "docs" / "x", tmp_path)
