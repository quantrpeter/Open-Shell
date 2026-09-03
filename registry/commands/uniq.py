"""uniq - extra command. Hosted on the website, not shipped on PyPI."""

from __future__ import annotations

from openshell import Records, command, get_field


@command("uniq", "Drop consecutive duplicates of a field", "uniq [.FIELD]")
def uniq(records: Records, args: list[str]) -> Records:
    field = args[0].lstrip(".") if args else None
    previous = object()
    for record in records:
        value = get_field(record, field) if field else record
        if value != previous:
            yield record
            previous = value
