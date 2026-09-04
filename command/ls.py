"""ls - list files as JSON records."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from openshell import Records, ShellError, command


@command("ls", "List files as JSON records", "ls [PATH] [-r] [-a]", source=True)
def fs_ls(_input: Records, args: list[str]) -> Records:
    target = Path(".")
    recursive = show_hidden = False
    for arg in args:
        if arg in ("-r", "--recursive"):
            recursive = True
        elif arg in ("-a", "--all"):
            show_hidden = True
        elif arg.startswith("-"):
            raise ShellError("arg.unknown", f"ls: unknown flag {arg!r}",
                             "supported flags: -r/--recursive, -a/--all")
        else:
            target = Path(arg).expanduser()

    if not target.exists():
        raise ShellError("fs.not_found", f"no such path: {target}",
                         "check the path, or run `ls` with no arguments")

    entries = target.rglob("*") if recursive else target.iterdir()
    for path in entries:
        if not show_hidden and path.name.startswith("."):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue  # vanished or unreadable mid-walk
        yield {
            "name": path.name,
            "path": str(path),
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(
                stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        }
