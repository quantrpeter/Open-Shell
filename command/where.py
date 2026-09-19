"""where - keep records matching a predicate."""

from __future__ import annotations

import re

from openshell import Records, ShellError, command, get_field, literal

PREDICATE_RE = re.compile(
	r"^\.(?P<field>[A-Za-z_][\w.]*)"
	r"(?:\s*(?P<op>>=|<=|==|!=|=~|>|<)\s*(?P<value>.+))?$"
)


@command("where", "Keep records matching a predicate", "where .FIELD [OP VALUE]")
def where(records: Records, args: list[str]) -> Records:
	expression = " ".join(args).strip()
	match = PREDICATE_RE.match(expression)
	if not match:
		raise ShellError("where.bad_predicate", f"cannot parse predicate: {expression!r}",
						 'try `where .size > 10mb` or `where .name =~ "\\.py$"`')

	field, op = match.group("field"), match.group("op")
	raw = match.group("value")
	wanted = literal(raw) if raw is not None else None
	pattern = re.compile(str(wanted)) if op == "=~" else None

	for record in records:
		value = get_field(record, field)
		if op is None:
			keep = bool(value)
		elif op == "=~":
			keep = value is not None and pattern.search(str(value)) is not None
		elif op == "==":
			keep = value == wanted
		elif op == "!=":
			keep = value != wanted
		else:
			try:
				keep = {
					">": lambda: value > wanted,
					"<": lambda: value < wanted,
					">=": lambda: value >= wanted,
					"<=": lambda: value <= wanted,
				}[op]()
			except TypeError:
				keep = False  # incomparable types simply don't match
		if keep:
			yield record
