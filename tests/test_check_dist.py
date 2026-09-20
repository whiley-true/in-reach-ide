"""The release gate (``.github/scripts/check_dist.py``): one pure-Python wheel and one sdist, for the release tag."""
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("check_dist", Path(__file__).parents[1] / ".github" / "scripts" / "check_dist.py")
check_dist = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_dist)

_WHEEL = "in_reach_ide-0.2.0-py3-none-any.whl"
_SDIST = "in_reach_ide-0.2.0.tar.gz"


def test_a_wheel_and_an_sdist_for_the_tag_are_fine() -> None:
    assert check_dist.problems([_WHEEL, _SDIST], "v0.2.0") == []


def test_a_platform_wheel_is_refused() -> None:
    assert any("py3-none-any" in p for p in check_dist.problems(["in_reach_ide-0.2.0-cp314-cp314-win_amd64.whl", _SDIST]))


def test_a_missing_sdist_or_wheel_is_reported() -> None:
    assert any("one sdist" in p for p in check_dist.problems([_WHEEL]))
    assert any("one wheel" in p for p in check_dist.problems([_SDIST]))


def test_a_version_that_is_not_the_tag_is_refused() -> None:
    assert any("release tag" in p for p in check_dist.problems([_WHEEL, _SDIST], "v0.3.0"))


def test_mixed_versions_and_strangers_are_refused() -> None:
    found = check_dist.problems([_WHEEL, "in_reach_ide-0.1.0.tar.gz", "notes.txt", "other-0.2.0-py3-none-any.whl"])

    assert any("more than one version" in p for p in found) and any("notes.txt" in p for p in found)
    assert any("not a in_reach_ide wheel" in p for p in found)
