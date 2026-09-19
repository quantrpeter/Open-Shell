"""install - download an extra command from the website registry."""

from __future__ import annotations

from openshell import Records, ShellError, command, install_from_catalog


@command("install", "Install an extra command from the website", "install NAME",
		 source=True)
def install(_input: Records, args: list[str]) -> Records:
	if len(args) != 1:
		raise ShellError("arg.missing", "install needs a command name",
						 "e.g. install count   (run `search` first)")
	yield install_from_catalog(args[0])
