"""count - extra command. Hosted on the website, not shipped on PyPI."""

from __future__ import annotations

from openshell import Records, command


@command("count", "Count incoming records", "count")
def count(records: Records, _args: list[str]) -> Records:
    n = 0
    for _ in records:
        n += 1
    yield {"count": n}
