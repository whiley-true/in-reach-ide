"""``app.run`` on a fresh install: the verification flow opens by itself once the window is up (in a file of its own:
``run`` re-applies the theme to every live widget, which is slow at the end of a long test file)."""
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from in_reach_ide import app as ide_app
from in_reach_ide.main_window import MainWindow


def test_run_opens_verification_once_the_window_is_up_on_a_fresh_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot
) -> None:
    project_dir = tmp_path / ".in-reach"
    project_dir.mkdir()
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    asked = []
    monkeypatch.setattr(MainWindow, "verify_on_first_run", lambda self: asked.append(self) or None)

    ide_app.run(project_dir)
    qtbot.waitUntil(lambda: bool(asked), timeout=2000)

    [window] = asked
    assert window.isVisible()  # scheduled, and run with the window already showing
    window.close()
    window.deleteLater()
