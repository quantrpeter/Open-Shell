"""mv - move or rename files."""

from __future__ import annotations

import shutil

from openshell import Records, ShellError, command, expand_path, file_record


@command("mv", "Move or rename files", "mv SRC … DEST", source=True)
def mv(_input: Records, args: list[str]) -> Records:
	if len(args) < 2:
		raise ShellError("arg.missing", "mv: SRC and DEST required",
						 "e.g. mv old_name.txt new_name.txt")
	dest = expand_path(args[-1])
	sources = [expand_path(path) for path in args[:-1]]
	many = len(sources) > 1

	if many and not dest.is_dir():
		raise ShellError("fs.not_dir", f"{dest} is not a directory",
						 "when moving multiple sources, DEST must be a folder")

	for source in sources:
		if not source.exists():
			raise ShellError("fs.not_found", f"no such path: {source}",
							 "check the source path")
		target = dest / source.name if dest.is_dir() else dest
		try:
			shutil.move(str(source), str(target))
		except OSError as err:
			raise ShellError("fs.move_failed", f"cannot move {source} to {target}: {err}",
							 "check the paths and permissions") from err
		record = file_record(target)
		if record is not None:
			yield record
