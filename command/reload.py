"""reload - re-read every command Python file from disk."""

from __future__ import annotations

from openshell import COMMANDS, Records, command, reload_commands


@command("reload", "Reload all command Python files", "reload", source=True)
def reload(_input: Records, _args: list[str]) -> Records:
    names, problems = reload_commands()
    for name in names:
        cmd = COMMANDS[name]
        yield {
            "name": cmd.name,
            "summary": cmd.summary,
            "usage": cmd.usage,
            "origin": cmd.origin,
            "status": "reloaded",
        }
    for err in problems:
        record = err.to_record()
        record["status"] = "failed"
        yield record
