"""command - list the loaded commands, as records."""

from __future__ import annotations

from openshell import COMMANDS, Records, command


@command("command", "List all loaded commands", "command", source=True)
def list_commands(_input: Records, _args: list[str]) -> Records:
    for name in sorted(COMMANDS):
        cmd = COMMANDS[name]
        yield {
            "name": cmd.name,
            "summary": cmd.summary,
            "usage": cmd.usage,
            "origin": cmd.origin,
        }
