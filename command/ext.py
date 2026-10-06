"""ext - run a program on PATH. External programs are never implicit."""

from __future__ import annotations

import os
import shutil

from openshell import Completion, Records, ShellError, command, run_external


@command("ext", "Run a program on PATH", "ext PROGRAM [ARGS …]", source=True)
def ext(_input: Records, args: list[str]) -> Records:
	if not args or args[0] in ("-h", "--help"):
		raise ShellError("arg.missing", "ext: PROGRAM required",
						 "e.g. ext ifconfig")
	name = args[0]
	path = shutil.which(name)
	if path is None:
		raise ShellError("exec.not_found", f"program not found: {name}",
						 "check PATH, or give the full path")
	yield from run_external(path, name, args[1:])


@ext.complete
d"""Complete the program name. Later words are the program's own arguments."""
	if len(ctx.tokens) > 1:
		return []
	names: list[str] = []
	seen: set[str] = set()
	for folder in os.environ.get("PATH", "").split(os.pathsep):
		if not folder:
			continue
		try:
			entries = os.listdir(folder)
		except OSError:
			continue
		for entry in entries:
			if entry in seen:
				continue
			path = os.path.join(folder, entry)
			if os.path.isfile(path) and os.access(path, os.X_OK):
				seen.add(entry)
				names.append(entry)
	return names
	return os.path.isfile(path) and os.access(path, os.X_OK)
