"""select - keep only the given fields."""

from __future__ import annotations

from openshell import Records, ShellError, command, get_field


@command("select", "Keep only the given fields", "select .FIELD [.FIELD ...]")
def select(records: Records, args: list[str]) -> Records:
	if not args:
		raise ShellError("select.no_fields", "select needs at least one field",
						 "e.g. select .name .size")
	fields = [arg.lstrip(".") for arg in args]
	for record in records:
		yield {field.split(".")[-1]: get_field(record, field) for field in fields}
