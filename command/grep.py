"""grep - search files or filter records for a pattern."""

from __future__ import annotations

import re
from typing import Any

from openshell import Records, ShellError, command, expand_path, iter_file_lines, parse_args


def _matches(value: Any, pattern: re.Pattern[str]) -> bool:
    if isinstance(value, str):
        return pattern.search(value) is not None
    if isinstance(value, dict):
        return any(_matches(item, pattern) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_matches(item, pattern) for item in value)
    return False


@command(
    "grep",
    "Search files or filter records for a pattern",
    "grep [-i] PATTERN [FILE …]",
    source=True,
    filter=True,
)
def grep(records: Records, args: list[str]) -> Records:
    flags, _opts, positionals = parse_args(
        args, "grep",
        flags={"-i": "ignore_case", "--ignore-case": "ignore_case"},
    )
    if not positionals:
        raise ShellError("arg.missing", "grep: PATTERN required",
                         'e.g. grep "error" app.log  or  ls | grep py')
    pattern_text, files = positionals[0], positionals[1:]
    flags_re = re.IGNORECASE if "ignore_case" in flags else 0
    try:
        pattern = re.compile(pattern_text, flags_re)
    except re.error as err:
        raise ShellError("grep.bad_pattern", f"bad pattern {pattern_text!r}: {err}",
                         "pass a valid regular expression") from err
    if files:
        for raw in files:
            for record in iter_file_lines(expand_path(raw)):
                if pattern.search(record["text"]):
                    yield record
        return
    for record in records:
        if _matches(record, pattern):
            yield record
