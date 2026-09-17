"""less - page through a file as line records."""

from __future__ import annotations

from openshell import Records, ShellError, command, expand_path, iter_file_lines, parse_args


@command("less", "Page through a file as line records", "less [-n N] FILE", source=True)
def less(_input: Records, args: list[str]) -> Records:
    _flags, opts, paths = parse_args(
        args, "less",
        valued={"-n": "n", "--lines": "n"},
    )
    if not paths:
        raise ShellError("arg.missing", "less: FILE required",
                         "e.g. less large_log.txt")
    page = 20
    if "n" in opts:
        try:
            page = int(opts["n"])
        except ValueError as err:
            raise ShellError("arg.bad", f"less: bad page size {opts['n']!r}",
                             "pass an integer, e.g. less -n 40 FILE") from err
        if page < 1:
            raise ShellError("arg.bad", "less: page size must be >= 1",
                             "e.g. less -n 20 FILE")
    count = 0
    for record in iter_file_lines(expand_path(paths[0])):
        yield record
        count += 1
        if count >= page:
            break
