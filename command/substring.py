"""substring - extract a slice of a string field (Python indexing)."""

from __future__ import annotations

from openshell import Json, Records, ShellError, command, get_field


def _set_field(record: dict, path: str, value: Json) -> dict:
    parts = path.split(".")
    root = dict(record)
    if len(parts) == 1:
        root[parts[0]] = value
        return root
    current: Json = root
    for part in parts[:-1]:
        nested = current.get(part) if isinstance(current, dict) else None
        copied = dict(nested) if isinstance(nested, dict) else {}
        current[part] = copied
        current = copied
    current[parts[-1]] = value
    return root


@command("substring", "Extract a substring from a field",
         "substring .FIELD START [END]")
def substring(records: Records, args: list[str]) -> Records:
    if len(args) < 2 or len(args) > 3:
        raise ShellError("substring.usage", "substring needs a field and indexes",
                         "e.g. substring .name 0 3")
    field = args[0].lstrip(".")
    if not field:
        raise ShellError("substring.no_field", "substring needs a field",
                         "e.g. substring .name 0 3")
    try:
        start = int(args[1])
        end = int(args[2]) if len(args) == 3 else None
    except ValueError:
        raise ShellError("substring.bad_index", "START and END must be integers",
                         "e.g. substring .name 0 3") from None

    for record in records:
        value = get_field(record, field)
        text = "" if value is None else str(value)
        sliced = text[start:] if end is None else text[start:end]
        if isinstance(record, dict):
            yield _set_field(record, field, sliced)
        else:
            yield sliced
