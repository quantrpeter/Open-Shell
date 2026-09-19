"""du - directory disk usage as records."""

from __future__ import annotations

from collections import deque
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


def _entries_up_to(root: Path, max_depth: int) -> list[Path]:
	"""Entries at relative depths 1..max_depth+1. Depth 0 is the root itself.

	`du -d0` is first-level children; `du -d1` is first- and second-level.
	"""
	found: list[Path] = []
	queue: deque[tuple[Path, int]] = deque([(root, 0)])
	while queue:
		current, depth = queue.popleft()
		if not current.is_dir() or depth >= max_depth + 1:
			continue
		try:
			children = sorted(current.iterdir(), key=lambda p: p.name)
		except OSError:
			continue
		for child in children:
			found.append(child)
			queue.append((child, depth + 1))
	return found


def _record(path: Path, human: bool) -> dict:
	size = _dir_size(path)
	record = {"path": str(path), "size": size}
	if human:
		record["size_h"] = human_size(size)
	return record


@command("du", "Directory disk usage", "du [-s] [-h] [-d N] [PATH …]", source=True)
def du(_input: Records, args: list[str]) -> Records:
	flags, opts, paths = parse_args(
		args, "du",
		flags={
			"-s": "summarize", "--summarize": "summarize",
			"-h": "human", "--human-readable": "human",
		},
		valued={
			"-d": "depth", "--max-depth": "depth",
		},
	)
	human = "human" in flags
	summarize = "summarize" in flags
	max_depth = 0
	if "depth" in opts:
		try:
			max_depth = int(opts["depth"])
		except ValueError as err:
			raise ShellError("arg.bad", f"du: bad depth {opts['depth']!r}",
							 "pass an integer, e.g. du -d1") from err
		if max_depth < 0:
			raise ShellError("arg.bad", "du: depth must be >= 0",
							 "e.g. du -d0")
	targets = [expand_path(path) for path in paths] or [Path(".")]

	for target in targets:
		if not target.exists():
			raise ShellError("fs.not_found", f"no such path: {target}",
							 "check the path")
		if summarize or target.is_file():
			yield _record(target, human)
			continue
		for child in _entries_up_to(target, max_depth):
			yield _record(child, human)
