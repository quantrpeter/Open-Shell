"""top / htop - list processes by CPU usage."""

from __future__ import annotations

from openshell import Records, ShellError, command, iter_processes, parse_args


def _by_cpu(records):
	rows = list(records)
	rows.sort(key=lambda row: row.get("cpu") or 0, reverse=True)
	return rows


@command("top", "List processes by CPU usage", "top [-n N]", source=True)
@command("htop", "List processes by CPU usage", "htop [-n N]", source=True)
def top(_input: Records, args: list[str]) -> Records:
	_flags, opts, _paths = parse_args(
		args, "top",
		valued={"-n": "n"},
	)
	limit = None
	if "n" in opts:
		try:
			limit = int(opts["n"])
		except ValueError as err:
			raise ShellError("arg.bad", f"top: bad count {opts['n']!r}",
							 "pass an integer, e.g. top -n 10") from err
	rows = _by_cpu(iter_processes())
	if limit is not None:
		rows = rows[:limit]
	yield from rows
