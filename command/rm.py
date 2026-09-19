"""rm - remove files or directories."""

from __future__ import annotations

import shutil

from openshell import Records, ShellError, command, expand_path, parse_args


@command("rm", "Remove files or directories", "rm [-r] [-f] PATH …", source=True)
def rm(_input: Records, args: list[str]) -> Records:
	flags, _opts, paths = parse_args(
		args, "rm",
		flags={
			"-r": "recursive", "--recursive": "recursive",
			"-f": "force", "--force": "force",
		},
	)
	if not paths:
		raise ShellError("arg.missing", "rm: PATH required",
						 "e.g. rm file.txt  or  rm -r old_folder")
	recursive = "recursive" in flags
	force = "force" in flags

	for raw in paths:
		path = expand_path(raw)
		if not path.exists():
			if force:
				continue
			raise ShellError("fs.not_found", f"no such path: {path}",
							 "use rm -f to ignore missing paths")
		try:
			if path.is_dir() and not path.is_symlink():
				if not recursive:
					raise ShellError("fs.is_dir", f"{path} is a directory",
									 "use rm -r to delete folders")
				shutil.rmtree(path)
			else:
				path.unlink()
		except ShellError:
			raise
		except OSError as err:
			if force:
				continue
			raise ShellError("fs.remove_failed", f"cannot remove {path}: {err}",
							 "check the path and permissions") from err
		yield {"path": str(path), "removed": True}
