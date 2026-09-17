"""ls - list files as JSON records."""

from __future__ import annotations

from pathlib import Path

from openshell import Records, ShellError, command, expand_path, file_record, parse_args


@command("ls", "List files as JSON records", "ls [PATH …] [-r] [-a] [-l]", source=True)
def fs_ls(_input: Records, args: list[str]) -> Records:
    flags, _opts, paths = parse_args(
        args, "ls",
        flags={
            "-a": "all", "--all": "all",
            "-r": "recursive", "--recursive": "recursive",
            "-l": "long", "--long": "long",
        },
    )
    targets = [expand_path(path) for path in paths] or [Path(".")]
    recursive = "recursive" in flags
    show_hidden = "all" in flags

    for target in targets:
        if not target.exists():
            raise ShellError("fs.not_found", f"no such path: {target}",
                             "check the path, or run `ls` with no arguments")
        if target.is_file():
            record = file_record(target)
            if record is not None:
                yield record
            continue
        entries = target.rglob("*") if recursive else target.iterdir()
        for path in entries:
            if not show_hidden and path.name.startswith("."):
                continue
            record = file_record(path)
            if record is not None:
                yield record

