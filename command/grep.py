"""grep - search line records for a pattern."""

from __future__ import annotations

import re

from openshell import Records, ShellError, command, expand_path, iter_file_lines, parse_args


@command("grep", "Search files for a pattern", "grep [-i] PATTERN [FILE …]", source=True)
def grep(_input: Records, args: list[str]) -> Records:
    flags, _opts, positionals = parse_args(
        args, "grep",
        flags={"-i": "ignore_case", "--ignore-case": "ignore_case"},
    )
    if not positionals:
        raise ShellError("arg.missing", "grep: PATTERN required",
                         'e.g. grep "error" app.log')
    pattern_text, files = positionals[0], positionals[1:]
    if not files:
        raise ShellError("arg.missing", "grep: FILE required",
                         'e.g. grep "error" app.log')
    flags_re = re.IGNORECASE if "ignore_case" in flags else 0
    try:
        pattern = re.compile(pattern_text, flags_re)
    except re.error as err:
        raise ShellError("grep.bad_pattern", f"bad pattern {pattern_text!r}: {err}",
                         "pass a valid regular expression") from err
    for raw in files:
        for record in iter_file_lines(expand_path(raw)):
            if pattern.search(record["text"]):
                yield record
