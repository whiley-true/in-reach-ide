"""``in-reach-ide`` / ``in-reach run``: the start-up checks and workspace bootstrap, never a real window."""
from pathlib import Path

import pytest
from click.testing import CliRunner

from in_reach import api
from in_reach.app import project
from in_reach_ide import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def stub_ide_launch(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Launching builds a real, blocking ``QApplication``; every test here is about what happens *before* that."""
    calls: list[Path] = []
    monkeypatch.setattr("in_reach_ide.app.run", lambda project_dir: calls.append(project_dir))
    return calls


def test_it_refuses_to_launch_off_windows(runner: CliRunner, tmp_path: Path, monkeypatch, stub_ide_launch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("in_reach_ide.cli.sys.platform", "linux")

    result = runner.invoke(cli.main, [])

    assert result.exit_code != 0 and "windows" in result.output.lower() and stub_ide_launch == []


def test_it_refuses_a_core_whose_api_it_does_not_know(runner: CliRunner, tmp_path: Path, monkeypatch, stub_ide_launch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("in_reach_ide.cli.sys.platform", "win32")
    monkeypatch.setattr(api, "API_VERSION", 99)

    result = runner.invoke(cli.main, [])

    assert result.exit_code != 0 and "API versions" in result.output and stub_ide_launch == []


def test_the_supported_range_includes_the_api_it_is_built_against() -> None:
    low, high = cli.SUPPORTED_API_VERSIONS

    assert low <= api.API_VERSION <= high


def test_it_launches_against_the_workspace_in_the_current_directory(runner: CliRunner, tmp_path: Path, monkeypatch, stub_ide_launch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("in_reach_ide.cli.sys.platform", "win32")

    result = runner.invoke(cli.main, [])

    assert result.exit_code == 0, result.output
    assert stub_ide_launch == [project.get_project_dir(tmp_path)]


def test_it_creates_the_workspace_on_first_run(runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("in_reach_ide.cli.sys.platform", "win32")

    runner.invoke(cli.main, [])

    project_dir = project.get_project_dir(tmp_path)
    assert (project_dir / ".env").is_file() and (project_dir / ".gitignore").is_file() and (project_dir / "README.md").is_file()
    values = dict(line.split("=", 1) for line in (project_dir / ".env").read_text().splitlines() if "=" in line)
    assert values["ROOT_DIR"] == str(tmp_path)


def test_launch_is_what_in_reach_run_calls(tmp_path: Path, monkeypatch, stub_ide_launch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("in_reach_ide.cli.sys.platform", "win32")

    cli.launch()

    assert stub_ide_launch == [project.get_project_dir(tmp_path)]
