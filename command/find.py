"""find - search for files by name, size, or modification date."""

from __future__ import annotations

import time
from fnmatch import fnmatch
from pathlib import Path

from openshell import (
	Records, ShellError, command, expand_path, file_record, literal, parse_args,
)


def _mtime_days(path: Path) -> float:
	return (time.time() - path.stat().st_mtime) / 86400


def _walk(root: Path, max_depth: int | None):
	"""Yield root, then descendants. Depth 1 is root's children.

	`max_depth` is the deepest relative level to enter. `None` walks everything.
	A file root yields only itself.
	"""
	yield root
	if not root.is_dir():
		return
	# (directory, depth of that directory). Children live one level deeper.
	stack: list[tuple[Path, int]] = [(root, 0)]
	while stack:
		current, depth = stack.pop()
		if max_depth is not None and depth >= max_depth:
			continue
		try:
			children = sorted(current.iterdir(), key=lambda item: item.name.lower())
		except OSError:
			continue
		child_depth = depth + 1
		# Push in reverse so a pop walks names in sorted order.
		for child in reversed(children):
			yield child
			if child.is_dir():
				stack.append((child, child_depth))


@command(
	"find",
	"Search for files by name, size, or age",
	"find [PATH] [-name GLOB] [-type f|d] [-size SIZE] [-mtime DAYS] [-d|--depth N]",
	source=True,
)
def find(_input: Records, args: list[str]) -> Records:
	_flags, opts, paths = parse_args(
		args, "find",
		valued={
			"-name": "name", "--name": "name",
			"-type": "type", "--type": "type",
			"-size": "size", "--size": "size",
			"-mtime": "mtime", "--mtime": "mtime",
			"-d": "depth", "--depth": "depth",
		},
	)
	root = expand_path(paths[0]) if paths else Path(".")
	if not root.exists():
		raise ShellError("fs.not_found", f"no such path: {root}",
						 "check the path")

	name_glob = opts.get("name")
	# `find . *.png` and `find . -name *.png` both filter by name.
	if name_glob is None:
		for path in paths[1:]:
			if any(char in path for char in "*?["):
				name_glob = path
				break
	kind = opts.get("type")
	if kind is not None and kind not in ("f", "d"):
		raise ShellError("arg.bad", f"find: unknown -type {kind!r}",
						 "use -type f or -type d")

	min_size = None
	if "size" in opts:
		min_size = literal(opts["size"])
		if not isinstance(min_size, (int, float)):
			raise ShellError("arg.bad", f"find: bad -size {opts['size']!r}",
							 "e.g. find . -size 10kb")

	max_age_days = None
	if "mtime" in opts:
		try:
			max_age_days = float(opts["mtime"])
		except ValueError as err:
			raise ShellError("arg.bad", f"find: bad -mtime {opts['mtime']!r}",
							 "pass a number of days, e.g. find . -mtime 7") from err

	max_depth = None
	if "depth" in opts:
		try:
			max_depth = int(opts["depth"])
		except ValueError as err:
			raise ShellError("arg.bad", f"find: bad depth {opts['depth']!r}",
							 "pass an integer, e.g. find . -d 2") from err
		if max_depth < 0:
			raise ShellError("arg.bad", "find: depth must be >= 0",
							 "0 lists only the start path; 1 lists its children")

	for path in _walk(root, max_depth):
		try:
			is_dir = path.is_dir()
			if kind == "f" and is_dir:
				continue
			if kind == "d" and not is_dir:
				continue
			if name_glob is not None and not fnmatch(path.name, name_glob):
				continue
			if min_size is not None and path.stat().st_size < min_size:
				continue
			if max_age_days is not None and _mtime_days(path) > max_age_days:
				continue
		except OSError:
			continue
		record = file_record(path)
		if record is not None:
			yield record
