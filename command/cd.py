"""cd - change the working directory."""

from __future__ import annotations

import os
from pathlib import Path

from openshell import Records, ShellError, command, expand_path


@command("cd", "Change the working directory", "cd [PATH]", source=True)
def cd(_input: Records, args: list[str]) -> Records:
    target = expand_path(args[0]) if args else Path.home()
    if not target.exists():
        raise ShellError("fs.not_found", f"no such path: {target}",
                         "check the path")
    if not target.is_dir():
        raise ShellError("fs.not_dir", f"{target} is not a directory",
                         "pass a folder")
    try:
        os.chdir(target)
    except OSError as err:
        raise ShellError("fs.chdir_failed", f"cannot cd to {target}: {err}",
                         "check the path and permissions") from err
    path = Path.cwd()
    yield {"path": str(path), "name": path.name}
