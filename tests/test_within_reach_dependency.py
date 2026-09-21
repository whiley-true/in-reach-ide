"""System detection (Tesseract, the Steam / Halo: MCC folders) comes from ``within-reach``, not from ``in-reach``."""
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).parents[1] / "src" / "in_reach_ide"


@pytest.mark.parametrize("module", ["welcome", "verify_dialog", "maps_panel", "explorer", "main_window"])
def test_each_screen_that_uses_the_detection_gets_it_from_within_reach(module: str) -> None:
    import importlib

    loaded = importlib.import_module(f"in_reach_ide.{module}")

    assert loaded.system_verify.__name__ == "within_reach.system_verify"


def test_no_source_file_reaches_for_the_cores_copy() -> None:
    offenders = [
        p.name for p in _SRC.glob("*.py")
        if re.search(r"in_reach\.app(\.system_verify|\s+import[^\n]*\bsystem_verify\b)", p.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_the_dependency_is_declared() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")

    assert '"within-reach>=0.2.0,<0.3"' in pyproject


def test_every_step_the_dialog_walks_is_within_reachs() -> None:
    from within_reach import system_verify

    from in_reach_ide import verify_dialog

    assert verify_dialog.STEPS is system_verify.STEPS and verify_dialog.VerifyRun is system_verify.VerifyRun
