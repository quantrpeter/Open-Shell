"""search - list extra commands from the website registry."""

from __future__ import annotations

from openshell import COMMANDS, Records, command, fetch_catalog, user_command_dir


@command("search", "Search website extras (not on PyPI)", "search [QUERY]", source=True)
def search(_input: Records, args: list[str]) -> Records:
	query = " ".join(args).lower()
	installed_dir = user_command_dir()
	for entry in fetch_catalog()["commands"]:
		if not isinstance(entry, dict):
			continue
		name = str(entry.get("name") or "")
		summary = str(entry.get("summary") or "")
		if query and query not in name.lower() and query not in summary.lower():
			continue
		filename = str(entry.get("file") or "").split("/")[-1]
		yield {
			"name": name,
			"summary": summary,
			"usage": entry.get("usage"),
			"tier": entry.get("tier", "extra"),
			"installed": (installed_dir / filename).is_file() or name in COMMANDS,
			"file": entry.get("file"),
		}
