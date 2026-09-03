"""remove - uninstall a website extra (never a pip built-in)."""

from __future__ import annotations

from openshell import Records, ShellError, command, remove_user_command


@command("remove", "Remove a website-installed extra", "remove NAME", source=True)
def remove(_input: Records, args: list[str]) -> Records:
    if len(args) != 1:
        raise ShellError("arg.missing", "remove needs a command name",
                         "e.g. remove count")
    yield remove_user_command(args[0])
