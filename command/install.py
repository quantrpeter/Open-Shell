"""install - download extras from the website registry or a GitHub repo."""

from __future__ import annotations

from openshell import Records, ShellError, command, install_source, reload_commands


@command("install", "Install extras from the website or a GitHub repo",
		 "install NAME|URL", source=True)
def install(_input: Records, args: list[str]) -> Records:
	if len(args) != 1:
		raise ShellError("arg.missing", "install needs a name or GitHub URL",
						 "e.g. install count, or install https://github.com/owner/Open-Shell-Mysql")
	record = install_source(args[0])
	reload_commands()
	yield record
