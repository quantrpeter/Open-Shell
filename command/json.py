"""json - display records in JSON format."""

from __future__ import annotations

from openshell import Records, ShellError, command, get_field, sort_key

@command("json", "display records in JSON format", "json")
def json(records: Records, args: list[str]) -> Records:
	import json
	for record in records:
		print(json.dumps(record))
	return records
