"""grep - search files or filter records for a pattern."""

from __future__ import annotations

import re
from typing import Any

from openshell import (
	Records, ShellError, command, expand_path, get_field, iter_file_lines, parse_args,
)


_FLAGS = {
	"-i": "ignore_case", "--ignore-case": "ignore_case",
	"-v": "invert", "--invert-match": "invert",
	"-F": "fixed", "--fixed-strings": "fixed",
	"-w": "word", "--word-regexp": "word",
	"-c": "count", "--count": "count",
	"-n": "line_number", "--line-number": "line_number",
}
_VALUED = {"--field": "field"}


def _matches(value: Any, pattern: re.Pattern[str]) -> bool:
	if isinstance(value, str):
		return pattern.search(value) is not None
	if isinstance(value, dict):
		return any(_matches(item, pattern) for item in value.values())
	if isinstance(value, (list, tuple)):
		return any(_matches(item, pattern) for item in value)
	return False


def _field_name(token: str) -> str | None:
	if token.startswith(".") and token != ".":
		return token[1:]
	return None


def _compile(text: str, *, ignore_case: bool, fixed: bool, word: bool) -> re.Pattern[str]:
	body = re.escape(text) if fixed else text
	if word:
		body = rf"\b(?:{body})\b"
	flags = re.IGNORECASE if ignore_case else 0
	try:
		return re.compile(body, flags)
	except re.error as err:
		raise ShellError("grep.bad_pattern", f"bad pattern {text!r}: {err}",
						 "pass a valid regular expression") from err


def _keep(matched: bool, invert: bool) -> bool:
	return not matched if invert else matched


@command(
	"grep",
	"Search files or filter records for a pattern",
	"grep [-i] [-v] [-F] [-w] [-c] [-n] [--field FIELD] [.FIELD] PATTERN [FILE …]",
	source=True,
	filter=True,
)
def grep(records: Records, args: list[str]) -> Records:
	flags, opts, positionals = parse_args(args, "grep", flags=_FLAGS, valued=_VALUED)
	field = opts.get("field")
	pattern_text: str | None = None
	files: list[str] = []
	for token in positionals:
		name = _field_name(token)
		if pattern_text is None and name is not None:
			if field is not None and field != name:
				raise ShellError(
					"arg.bad",
					f"grep: field {name!r} does not match --field {field!r}",
					"pass one field, as .name or --field name",
				)
			field = name
			continue
		if pattern_text is None:
			pattern_text = token
			continue
		files.append(token)
	if pattern_text is None:
		raise ShellError("arg.missing", "grep: PATTERN required",
						 'e.g. grep "error" app.log  or  ls | grep py')
	if field and files:
		raise ShellError(
			"arg.bad",
			"grep: a field filter cannot be combined with files",
			"use the field on a pipeline, e.g. ls | grep .name py",
		)
	pattern = _compile(
		pattern_text,
		ignore_case="ignore_case" in flags,
		fixed="fixed" in flags,
		word="word" in flags,
	)
	invert = "invert" in flags
	count_only = "count" in flags

	if files:
		for raw in files:
			path = expand_path(raw)
			count = 0
			for record in iter_file_lines(path):
				if _keep(pattern.search(record["text"]) is not None, invert):
					count += 1
					if not count_only:
						yield record
			if count_only:
				yield {"path": str(path), "count": count}
		return

	count = 0
	for record in records:
		if field:
			value = get_field(record, field)
			matched = value is not None and pattern.search(str(value)) is not None
		else:
			matched = _matches(record, pattern)
		if _keep(matched, invert):
			count += 1
			if not count_only:
				yield record
	if count_only:
		yield {"count": count}


@grep.help
def grep_help() -> None:
	print("grep [-i] [-v] [-F] [-w] [-c] [-n] [--field FIELD] [.FIELD] PATTERN [FILE …]")
	print("  Search files, or filter pipeline records. PATTERN is a Python regex.")
	print("  .FIELD, --field FIELD   Match one field (pipeline only)")
	print("  -i, --ignore-case       Case-insensitive match")
	print("  -v, --invert-match      Keep non-matches")
	print("  -F, --fixed-strings     PATTERN is literal text")
	print("  -w, --word-regexp       Match a whole word")
	print("  -c, --count             Yield counts only")
	print("  -n, --line-number       File records include n (always present)")
	print("  --help                  Show this help")
