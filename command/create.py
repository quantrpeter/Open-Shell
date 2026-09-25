"""create - write sample files, starting with ~/.openshell."""

from __future__ import annotations

import json

from openshell import (
	Records,
	ShellError,
	command,
	file_record,
	load_env,
	parse_args,
	env_path,
)

SAMPLE_SETTINGS = {
	"ai": "xai",
	"ai_key": "...",
	"ai_mode": "grok-4.6",
}

TARGETS = {".openshell", "~/.openshell"}


@command("create", "Create sample files", "create .openshell [--force]", source=True)
def create(_input: Records, args: list[str]) -> Records:
	flags, _opts, targets = parse_args(
		args, "create",
		flags={"-f": "force", "--force": "force"},
	)
	if len(targets) != 1:
		raise ShellError("arg.missing", "create: target required",
						 "e.g. create .openshell")
	target = targets[0]
	if target not in TARGETS:
		raise ShellError("create.unknown", f"unknown create target: {target!r}",
						 "supported: create .openshell")

	path = env_path()
	if path.exists() and "force" not in flags:
		raise ShellError("fs.exists", f"already exists: {path}",
						 "delete it first, or pass --force")
	try:
		path.write_text(json.dumps(SAMPLE_SETTINGS, indent=2) + "\n", encoding="utf-8")
	except OSError as err:
		raise ShellError("fs.write_failed", f"cannot write {path}: {err}",
						 "check the path and permissions") from err

	problem = load_env()
	if problem is not None:
		raise problem

	record = file_record(path)
	if record is not None:
		yield record


@create.complete
def create_complete(ctx) -> list[str]:
	"""Tab-complete the sample-file target. Flags stay with the core."""
	return sorted(target for target in TARGETS if target.startswith(ctx.word))
