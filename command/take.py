"""take - keep the first N records."""

from __future__ import annotations

from openshell import Records, ShellError, command


@command("take", "Keep the first N records", "take N")
def take(records: Records, args: list[str]) -> Records:
	if len(args) != 1 or not args[0].isdigit():
		raise ShellError("take.bad_count", "take needs a record count", "e.g. take 10")
	limit = int(args[0])
	for index, record in enumerate(records):
		if index >= limit:
			break  # closes the upstream generator: laziness for free
		yield record
