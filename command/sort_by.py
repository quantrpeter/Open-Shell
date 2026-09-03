"""sort-by - order records by a field. Blocking: buffers the whole stream."""

from __future__ import annotations

from openshell import Records, ShellError, command, get_field, sort_key


@command("sort-by", "Sort records by a field (blocking)", "sort-by .FIELD [--desc]")
def sort_by(records: Records, args: list[str]) -> Records:
    field = None
    descending = False
    for arg in args:
        if arg in ("-d", "--desc"):
            descending = True
        elif arg.startswith("."):
            field = arg.lstrip(".")
        else:
            raise ShellError("arg.unknown", f"sort-by: unexpected {arg!r}",
                             "e.g. sort-by .size --desc")
    if field is None:
        raise ShellError("sort-by.no_field", "sort-by needs a field",
                         "e.g. sort-by .size --desc")

    yield from sorted(records, key=lambda r: sort_key(get_field(r, field)),
                      reverse=descending)
