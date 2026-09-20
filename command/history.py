"""history - list previously run commands as records."""

from __future__ import annotations

import json
import re

from openshell import Records, ShellError, command, history_path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
RECORD_COUNT_RE = re.compile(r"\(\d+ records?\)")


def _parse_history_line(text: str) -> dict:
	try:
		record = json.loads(text)
	except json.JSONDecodeError:
		return {"command": text, "timestamp": "", "result": ""}
	if not isinstance(record, dict):
		return {"command": text, "timestamp": "", "result": ""}
	return {
		"command": record.get("command", text),
		"timestamp": record.get("timestamp", ""),
		"result": record.get("result", ""),
	}


@command("history", "List previously run commands", "history [N]", source=True)
def history(_input: Records, args: list[str]) -> Records:
	path = history_path()
	if not path.is_file():
		return

	try:
		lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
	except OSError as err:
		raise ShellError("fs.read_failed", f"cannot read {path}: {err}",
						 "check the path and permissions") from err

	start = 1
	if args:
		try:
			limit = int(args[0])
		except ValueError as err:
			raise ShellError("arg.bad", f"history: bad count {args[0]!r}",
							 "pass an integer, e.g. history 10") from err
		if limit < 0:
			raise ShellError("arg.bad", "history: count must be >= 0",
							 "e.g. history 10")
		if limit == 0:
			return
		start = max(1, len(lines) - limit + 1)
		lines = lines[-limit:]

	for number, text in enumerate(lines, start):
		record = _parse_history_line(text)
		result = ANSI_RE.sub("", str(record["result"]))
		result = RECORD_COUNT_RE.sub("", result)
		result = result.replace("\n", " ").strip()
		yield {
			"n": number,
			"timestamp": record["timestamp"],
			"command": record["command"],
			"result": result,
		}
