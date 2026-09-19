"""tail - last N lines of a file as records."""

from __future__ import annotations

from collections import deque

from openshell import Records, ShellError, command, expand_path, iter_file_lines, parse_args


@command("tail", "Last N lines of a file", "tail [-n N] [-f] FILE", source=True)
def tail(_input: Records, args: list[str]) -> Records:
	flags, opts, paths = parse_args(
		args, "tail",
		flags={"-f": "follow", "--follow": "follow"},
		valued={"-n": "n"},
	)
	if not paths:
		raise ShellError("arg.missing", "tail: FILE required",
						 "e.g. tail -n 10 app.log")
	if "follow" in flags:
		raise ShellError("arg.unsupported", "tail -f is not supported yet",
						 "use tail -n N FILE")
	limit = 10
	if "n" in opts:
		try:
			limit = int(opts["n"])
		except ValueError as err:
			raise ShellError("arg.bad", f"tail: bad line count {opts['n']!r}",
							 "pass an integer, e.g. tail -n 10 FILE") from err
		if limit < 0:
			raise ShellError("arg.bad", "tail: line count must be >= 0",
							 "e.g. tail -n 10 FILE")
	buffer: deque[dict] = deque(maxlen=limit)
	for record in iter_file_lines(expand_path(paths[0])):
		buffer.append(record)
	yield from buffer
