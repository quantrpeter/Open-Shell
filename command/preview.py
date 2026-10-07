"""preview - open a file in the preview panel."""

from __future__ import annotations

from openshell import Records, ShellError, command, expand_path, file_record


@command("preview", "Open a file in the preview panel", "preview FILE", source=True)
def preview(_input: Records, args: list[str]) -> Records:
	if not args:
		raise ShellError("arg.missing", "preview: FILE required", "e.g. preview readme.md")
	target = expand_path(args[0])
	if not target.exists():
		raise ShellError("fs.not_found", f"no such path: {target}", "check the path")
	if target.is_dir():
		raise ShellError("fs.is_dir", f"{target} is a directory", "pass a file")
	record = file_record(target)
	if record is None:
		raise ShellError("fs.read_failed", f"cannot stat {target}", "check the path and permissions")
	record["$t"] = "preview"
	yield record
