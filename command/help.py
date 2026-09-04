"""help - list the loaded commands, as records.

Introspection goes through the pipeline like any other data, so
`help | where .origin =~ "^fs" | select .name .usage` works.
"""

from __future__ import annotations

from openshell import COMMANDS, Records, command


@command("help", "List loaded commands as records", "help [NAME]", source=True)
@command("?", "List loaded commands as records", "help [NAME]", source=True)
def help(_input: Records, args: list[str]) -> Records:
    wanted = args[0] if args else None
    for name in sorted(COMMANDS):
        cmd = COMMANDS[name]
        if wanted is None or wanted == name:
            yield {
                "name": cmd.name,
                "summary": cmd.summary,
                "usage": cmd.usage,
                "origin": cmd.origin,
            }
