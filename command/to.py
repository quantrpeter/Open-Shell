"""to - render the stream. `to json` for machines, `to table` for humans.

Sinks consume records and write to stdout; every other command must stay
silent and yield records instead.
"""

from __future__ import annotations

import json
import sys

from openshell import ENV, Json, Records, ShellError, command, use_color, format_datetime

DEFAULT_WIDTH = 80


def table_width() -> int:
	value = ENV.get("width", DEFAULT_WIDTH)
	try:
		width = int(value)
	except (TypeError, ValueError):
		return DEFAULT_WIDTH
	return width if width >= 1 else DEFAULT_WIDTH


def render_cell(value: Json) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, (dict, list)):
		return json.dumps(value, default=str)
	return str(value)


def fit(text: str) -> str:
	"""Truncate visibly, keeping the tail - the distinctive part of a path."""
	width = table_width()
	return text if len(text) <= width else text[0:width]+"…"


def render_table(rows: list[Json]) -> None:
	if not all(isinstance(row, dict) for row in rows):
		for row in rows:
			sys.stdout.write(json.dumps(row, default=str) + "\n")
		return

	columns: list[str] = []
	for row in rows:
		for key in row:
			if key not in columns:
				columns.append(key)
		for key in ("modified", "timestamp"):
			if key in row and row[key] not in (None, ""):
				row[key] = format_datetime(row[key])

	cells = [{c: fit(render_cell(row.get(c))) for c in columns} for row in rows]
	widths = {c: max(len(c), max(len(cell[c]) for cell in cells)) for c in columns}
	numeric = {
		c: all(isinstance(row.get(c), (int, float)) and not isinstance(row.get(c), bool)
			   for row in rows if row.get(c) is not None)
		for c in columns
	}

	def line(values: dict[str, str], bold: bool = False) -> None:
		parts = [values[c].rjust(widths[c]) if numeric[c] else values[c].ljust(widths[c])
				 for c in columns]
		text = "  ".join(parts).rstrip()
		if bold and use_color(sys.stdout):
			text = f"\033[1m{text}\033[0m"
		sys.stdout.write(text + "\n")

	line({c: c for c in columns}, bold=True)
	line({c: "-" * widths[c] for c in columns})
	for cell in cells:
		line(cell)
	sys.stdout.write(f"({len(rows)} record{'s' if len(rows) != 1 else ''})\n")


@command("to", "Render the stream: `to json` or `to table`", "to json|table [--compact]")
def to(records: Records, args: list[str]) -> tuple[Json, ...]:
	fmt = args[0] if args else "table"
	flags = args[1:]

	if fmt == "json":
		separators = (",", ":") if "--compact" in flags else None
		for record in records:
			sys.stdout.write(
				json.dumps(record, default=str, separators=separators) + "\n")
	elif fmt == "table":
		rows = list(records)
		if rows:
			render_table(rows)
		else:
			sys.stdout.write("(no records)\n")
	else:
		raise ShellError("to.unknown_format", f"unknown output format: {fmt!r}",
						 "supported formats: json, table")
	return ()
