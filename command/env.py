"""env - list loaded Open Shell settings."""

from __future__ import annotations

from openshell import ENV, Records, command


@command("env", "Dump all loaded settings", "env", source=True)
def env(_input: Records, _args: list[str]) -> Records:
	for name in sorted(ENV):
		yield {"name": name, "value": ENV[name]}