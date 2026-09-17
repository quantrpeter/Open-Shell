"""mkdir - create directories."""

from __future__ import annotations

from openshell import Records, ShellError, command, expand_path, file_record, parse_args


@command("mkdir", "Create directories", "mkdir [-p] PATH …", source=True)
def mkdir(_input: Records, args: list[str]) -> Records:
    flags, _opts, paths = parse_args(
        args, "mkdir",
        flags={"-p": "parents", "--parents": "parents"},
    )
    if not paths:
        raise ShellError("arg.missing", "mkdir: PATH required",
                         "e.g. mkdir new_folder")
    parents = "parents" in flags
    for raw in paths:
        path = expand_path(raw)
        try:
            path.mkdir(parents=parents, exist_ok=parents)
        except FileExistsError as err:
            raise ShellError("fs.exists", f"already exists: {path}",
                             "use mkdir -p to ignore existing directories") from err
        except OSError as err:
            raise ShellError("fs.mkdir_failed", f"cannot mkdir {path}: {err}",
                             "check the path and permissions") from err
        record = file_record(path)
        if record is not None:
            yield record
