"""The ``in-reach-ide`` command, and what ``in-reach run`` calls: open the IDE.

Kept apart from :mod:`in_reach_ide.app` (which builds the ``QApplication``) so a test can drive the start-up -- workspace
bootstrap, platform and API-version checks -- without ever constructing a window.
"""

from __future__ import annotations

import sys

import click

from in_reach import api

#: The range of ``in_reach.api.API_VERSION`` this IDE was written against (inclusive).
SUPPORTED_API_VERSIONS = (1, 1)


def check_environment() -> None:
    """Refuses to start where the IDE can't work: not Windows (its frameless window handling is Windows-specific), or
    against a core library whose API this version doesn't know."""
    if sys.platform != "win32":
        raise click.ClickException("in-reach's IDE is Windows-only.")
    low, high = SUPPORTED_API_VERSIONS
    if not low <= api.API_VERSION <= high:
        raise click.ClickException(
            f"this in-reach-ide works with in-reach API versions {low}-{high}, but in-reach provides {api.API_VERSION}; "
            "upgrade or downgrade one of them."
        )


def launch() -> None:
    """Prepares the workspace in the current directory (``.in-reach`` folder, ``.env``, logging) and opens the IDE,
    fullscreen, blocking until the window closes."""
    check_environment()
    project_dir = api.prepare_workspace()
    from in_reach_ide import app as ide_app

    ide_app.run(project_dir)


@click.command()
@click.version_option(package_name="in-reach-ide")
def main() -> None:
    """Open the in-reach IDE, fullscreen."""
    launch()
