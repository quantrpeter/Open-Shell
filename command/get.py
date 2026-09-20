"""get - read a setting from ~/.openshell."""

from __future__ import annotations

from openshell import ENV, Records, ShellError, command, load_env


@command("get", "Get a setting from ~/.openshell", "get NAME", source=True)
def get_setting(_input: Records, args: list[str]) -> Records:
	if len(args) != 1:
		raise ShellError("arg.missing", "get: NAME required",
						 "e.g. get ai_key   (or `env` for every setting)")
	name = args[0]
	problem = load_env()
	if problem is not None:
		raise problem
	if name not in ENV:
		raise ShellError("settings.missing", f"no setting named {name!r}",
						 "run `env` to list settings, or `set NAME VALUE`")
	yield {"name": name, "value": ENV[name]}
