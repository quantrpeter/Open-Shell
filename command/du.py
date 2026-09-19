"""du - directory disk usage as records."""

from __future__ import annotations

from pathlib import Path

from openshell import Records, ShellError, command, expand_path, human_size, parse_args


def _dir_size(path: Path) -> int:
	if path.is_file():
		try:
			return path.stat().st_size
		except OSError:
			return 0
	total = 0
	for child in path.rglob("*"):
		try:
			if child.is_file():
				total += child.stat().st_size
		except OSError:
			continue
	return total


@command("du", "Directory disk usage", "du [-s] [-h] [PATH …]", source=True)
def du(_input: Records, args: list[str]) -> Records:
	flags, _opts, paths = parse_args(
		args, "du",
		flags={
			"-s": "summarize", "--summarize": "summarize",
			"-h": "human", "--human-readable": "human",
		},
	)
	human = "human" in flags
	summarize = "summarize" in flags or not paths
	targets = [expand_path(path) for path in paths] or [Path(".")]

	for target in targets:
		if not target.exists():
			raise ShellError("fs.not_found", f"no such path: {target}",
							 "check the path")
		if summarize or target.is_file():
			size = _dir_size(target)
			record = {"path": str(target), "size": size}
			if human:
				record["size_h"] = human_size(size)
			yield record
			continue
		for child in sorted(target.iterdir(), key=lambda p: p.name):
			size = _dir_size(child)
			record = {"path": str(child), "size": size}
			if human:
				record["size_h"] = human_size(size)
			yield record
