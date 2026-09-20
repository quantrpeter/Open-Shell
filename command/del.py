"""del - delete a setting from ~/.openshell."""

from __future__ import annotations

from openshell import Records, SETTINGS, ShellError, command, load_settings, save_settings


@command("del", "Delete a setting and save ~/.openshell", "del NAME", source=True)
def del_setting(_input: Records, args: list[str]) -> Records:
	if len(args) != 1:
		raise ShellError("arg.missing", "del: NAME required",
						 "e.g. del ai_key   (or `env` for every setting)")
	name = args[0]
	problem = load_settings()
	if problem is not None:
		raise problem
	if name not in SETTINGS:
		raise ShellError("settings.missing", f"no setting named {name!r}",
						 "run `env` to list settings")
	value = SETTINGS.pop(name)
	save_settings()
	yield {"name": name, "value": value, "status": "deleted"}
