"""df - disk space usage as records."""

from __future__ import annotations

import shutil

from openshell import Records, command, expand_path, human_size, parse_args


@command("df", "Disk space usage", "df [-h] [PATH …]", source=True)
def df(_input: Records, args: list[str]) -> Records:
	flags, _opts, paths = parse_args(
		args, "df",
		flags={"-h": "human", "--human-readable": "human"},
	)
	human = "human" in flags
	targets = [expand_path(path) for path in paths] or [expand_path("/")]

	for target in targets:
		try:
			usage = shutil.disk_usage(target)
		except OSError:
			continue
		total, used, free = usage.total, usage.used, usage.free
		percent = int(round((used / total) * 100)) if total else 0
		record = {
			"path": str(target),
			"total": total,
			"used": used,
			"available": free,
			"percent": percent,
		}
		if human:
			record["total_h"] = human_size(total)
			record["used_h"] = human_size(used)
			record["available_h"] = human_size(free)
		yield record
