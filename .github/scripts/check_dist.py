"""Checks that ``dist/`` holds exactly what a release should publish, before anything is uploaded to PyPI.

    python .github/scripts/check_dist.py dist --tag v0.2.0

Exits 0 if it does, otherwise prints every problem and exits 1. ``publish.yml`` runs it between building and
``pypa/gh-action-pypi-publish``, because that action uploads whatever is in the folder and a PyPI version can never be
uploaded again.

What it expects: one sdist and one pure-Python wheel (``py3-none-any`` -- this package has no compiled code), both for
the same version, and that version equal to the release tag if one is given; nothing else.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DISTRIBUTION = "in_reach_ide"

_WHEEL = re.compile(r"^(?P<name>[^-]+)-(?P<version>[^-]+)-(?P<python>[^-]+)-(?P<abi>[^-]+)-(?P<platform>[^-]+)\.whl$")
_SDIST = re.compile(r"^(?P<name>[^-]+)-(?P<version>.+)\.tar\.gz$")


def problems(filenames: list[str], tag: str | None = None) -> list[str]:
    """Everything wrong with ``filenames`` (the names in ``dist/``) for a release; empty if it's fine."""
    found: list[str] = []
    versions: set[str] = set()
    wheels = sdists = 0

    for name in sorted(filenames):
        wheel = _WHEEL.match(name)
        sdist = _SDIST.match(name)
        if wheel:
            wheels += 1
            versions.add(wheel["version"])
            if wheel["name"] != DISTRIBUTION:
                found.append(f"{name}: not a {DISTRIBUTION} wheel")
            if (wheel["python"], wheel["abi"], wheel["platform"]) != ("py3", "none", "any"):
                found.append(f"{name}: expected a py3-none-any wheel")
        elif sdist:
            sdists += 1
            versions.add(sdist["version"])
            if sdist["name"] != DISTRIBUTION:
                found.append(f"{name}: not a {DISTRIBUTION} sdist")
        else:
            found.append(f"{name}: not a wheel or an sdist")

    if wheels != 1:
        found.append(f"expected exactly one wheel, found {wheels}")
    if sdists != 1:
        found.append(f"expected exactly one sdist, found {sdists}")
    if len(versions) > 1:
        found.append(f"more than one version in dist/: {', '.join(sorted(versions))}")
    if tag is not None and versions and versions != {tag.removeprefix("v")}:
        found.append(f"dist/ is version {', '.join(sorted(versions))}, but the release tag is {tag}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist", type=Path)
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)
    names = [p.name for p in args.dist.iterdir() if p.is_file()] if args.dist.is_dir() else []
    found = problems(names, args.tag)
    for problem in found:
        print(f"error: {problem}", file=sys.stderr)
    if not found:
        print(f"ok: {', '.join(sorted(names))}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
