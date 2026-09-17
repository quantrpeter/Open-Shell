"""pwd - print the working directory as a record."""

from __future__ import annotations

from pathlib import Path

from openshell import Records, command


@command("pwd", "Print the working directory", "pwd", source=True)
def pwd(_input: Records, _args: list[str]) -> Records:
    path = Path.cwd()
    yield {"path": str(path), "name": path.name}
