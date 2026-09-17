"""ps - list running processes as records."""

from __future__ import annotations

from openshell import Records, command, iter_processes, parse_args


@command("ps", "List running processes", "ps [aux]", source=True)
def ps(_input: Records, args: list[str]) -> Records:
    normalized: list[str] = []
    for arg in args:
        if arg and not arg.startswith("-") and arg.isalpha() and set(arg) <= set("auxew"):
            normalized.append("-" + arg)
        else:
            normalized.append(arg)
    parse_args(
        normalized, "ps",
        flags={
            "-a": "all", "-u": "user", "-x": "x", "-e": "all", "-w": "wide",
            "--all": "all",
        },
    )
    yield from iter_processes()
