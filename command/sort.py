"""sort - order records by a field. Blocking: buffers the whole stream."""

from __future__ import annotations

from openshell import Records, ShellError, command, get_field, sort_key


@command("sort", "Sort records by a field (blocking)", "sort .FIELD [--desc]")
def sort(records: Records, args: list[str]) -> Records:
    field = None
    descending = False
    for arg in args:
        if arg in ("-d", "--desc"):
            descending = True
        elif arg.startswith("."):
            field = arg.lstrip(".")
        else:
            raise ShellError("arg.unknown", f"sort: unexpected {arg!r}",
                             "e.g. sort .size --desc")
    if field is None:
        raise ShellError("sort.no_field", "fuck sort needs a field",
                         "e.g. sort .size --desc")

    yield from sorted(records, key=lambda r: sort_key(get_field(r, field)),
                      reverse=descending)
