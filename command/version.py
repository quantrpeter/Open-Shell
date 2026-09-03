"""version - report version and runtime info."""

from __future__ import annotations

import sys

from openshell import COMMANDS, Records, __version__, command


@command("version", "Show version and runtime info", "version", source=True)
def version(_input: Records, _args: list[str]) -> Records:
    yield {
        "name": "openshell",
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "commands": len(COMMANDS),
    }
