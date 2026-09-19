"""cat - read files as line records."""

from __future__ import annotations

from openshell import Records, ShellError, command, expand_path, iter_file_lines


@command("cat", "Read files as line records", "cat FILE …", source=True)
def cat(_input: Records, args: list[str]) -> Records:
	if not args:
		raise ShellError("arg.missing", "cat: FILE required",
						 "e.g. cat config.txt")
	for raw in args:
		for record in iter_file_lines(expand_path(raw)):
			del record["path"]
			yield record
