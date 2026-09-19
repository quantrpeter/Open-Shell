"""head - first N lines of a file as records."""

from __future__ import annotations

from openshell import Records, ShellError, command, expand_path, iter_file_lines, parse_args


@command("head", "First N lines of a file", "head [-n N] FILE", source=True)
def head(_input: Records, args: list[str]) -> Records:
	_flags, opts, paths = parse_args(
		args, "head",
		valued={"-n": "n"},
	)
	if not paths:
		raise ShellError("arg.missing", "head: FILE required",
						 "e.g. head -n 10 config.txt")
	limit = 10
	if "n" in opts:
		try:
			limit = int(opts["n"])
		except ValueError as err:
			raise ShellError("arg.bad", f"head: bad line count {opts['n']!r}",
							 "pass an integer, e.g. head -n 10 FILE") from err
		if limit < 0:
			raise ShellError("arg.bad", "head: line count must be >= 0",
							 "e.g. head -n 10 FILE")
	count = 0
	for record in iter_file_lines(expand_path(paths[0])):
		if count >= limit:
			break
		yield record
		count += 1
