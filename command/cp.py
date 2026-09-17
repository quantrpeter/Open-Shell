"""cp - copy files or directories."""

from __future__ import annotations

import shutil

from openshell import Records, ShellError, command, expand_path, file_record, parse_args


@command("cp", "Copy files or directories", "cp [-r] SRC … DEST", source=True)
def cp(_input: Records, args: list[str]) -> Records:
    flags, _opts, paths = parse_args(
        args, "cp",
        flags={"-r": "recursive", "--recursive": "recursive"},
    )
    if len(paths) < 2:
        raise ShellError("arg.missing", "cp: SRC and DEST required",
                         "e.g. cp file.txt backup.txt")
    dest = expand_path(paths[-1])
    sources = [expand_path(path) for path in paths[:-1]]
    recursive = "recursive" in flags
    many = len(sources) > 1

    if many and not dest.is_dir():
        raise ShellError("fs.not_dir", f"{dest} is not a directory",
                         "when copying multiple sources, DEST must be a folder")

    for source in sources:
        if not source.exists():
            raise ShellError("fs.not_found", f"no such path: {source}",
                             "check the source path")
        if source.is_dir() and not recursive:
            raise ShellError("fs.is_dir", f"{source} is a directory",
                             "use cp -r to copy folders")
        target = dest / source.name if dest.is_dir() else dest
        try:
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                if target.parent and not target.parent.exists():
                    raise ShellError("fs.not_found", f"no such path: {target.parent}",
                                     "create the destination folder first")
                shutil.copy2(source, target)
        except ShellError:
            raise
        except OSError as err:
            raise ShellError("fs.copy_failed", f"cannot copy {source} to {target}: {err}",
                             "check the paths and permissions") from err
        record = file_record(target)
        if record is not None:
            yield record
