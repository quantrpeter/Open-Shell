"""pwd - print the working directory as a record."""

from __future__ import annotations

import os
from pathlib import Path

from openshell import Records, command


@command("pwd", "Print the working directory", "pwd", source=True)
def pwd(_input: Records, _args: list[str]) -> Records:
    logical = os.environ.get("PWD")
    path = Path(logical) if logical else Path.cwd()
    try:
        if logical and not os.path.samefile(logical, os.getcwd()):
            path = Path.cwd()
    except OSError:
        path = Path.cwd()
    yield {"path": str(path), "name": path.name}
