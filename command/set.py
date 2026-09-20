"""set - write a setting to ~/.openshell."""

from __future__ import annotations

from openshell import (
	ENV, Records, ShellError, command, literal, load_env, save_settings,
)


@command("set", "Set a setting and save ~/.openshell", "set NAME VALUE …",
		 source=True)
def set_setting(_input: Records, args: list[str]) -> Records:
	if len(args) < 2:
		raise ShellError("arg.missing", "set: NAME and VALUE required",
						 'e.g. set ai xai   or   set ai_key "…"')
	name = args[0]
	if not name or name.startswith("-"):
		raise ShellError("arg.bad", f"set: bad name {name!r}",
						 "use a setting name such as ai, ai_key, mysql_host")
	problem = load_env()
	if problem is not None:
		raise problem
	value = literal(" ".join(args[1:]))
	ENV[name] = value
	save_settings()
	yield {"name": name, "value": value}
