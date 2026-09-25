# Plan: Enrich grep

Keep current `-i` and Python-regex behavior. Add a pipeline field filter (`ls | grep .name abc`) plus `-v`, `-F`, `-w`, `-c`, and `-n`. Change only `command/grep.py` and the README command row. Do not change `parse_args` or `where`.

## Steps

1. Update usage to `grep [-i] [-v] [-F] [-w] [-c] [-n] [--field FIELD] [.FIELD] PATTERN [FILE …]`. Add `@grep.help` in the same style as `ls_help`.
2. Parse flags with existing `parse_args`. No core parser change: a token like `.name` is already positional because it does not start with `-`.
3. Field: if a positional starts with `.` and sits before PATTERN, strip the leading dot (same as `select`) and treat it as the field. Also accept `--field` / `--field=`. One field only. If both forms are set and they differ, raise `arg.bad`.
4. Field matching is pipeline-only. If a field is set and FILE args are present, raise `arg.bad` (do not silently ignore). Match `get_field(record, field)` only — do not walk the whole record. `None` does not match. Other values are matched as `str(value)` so `.size` can match. Without a field, keep recursive `_matches` on string values.
5. Compile one pattern: default is Python `re.search` (not fullmatch). `-F` / `--fixed-strings` runs `re.escape` first. `-w` / `--word-regexp` wraps the (possibly escaped) pattern in `\b(?:...)\b`. `-i` / `--ignore-case` stays `re.IGNORECASE`. Bad pattern stays `grep.bad_pattern`. Missing PATTERN stays `arg.missing`.
6. `-v` / `--invert-match` inverts the keep decision in both file and pipeline modes, including field mode.
7. `-c` / `--count` yields counts only, never match rows. Pipeline: one `{"count": N}`. Files: one `{"path", "count"}` per file. Count after invert.
8. `-n` / `--line-number` is accepted for compatibility. File mode already yields `n` via `iter_file_lines`; do not strip it. Do not invent line numbers on pipeline records.
9. Update the README command-table row for `grep`. Do not change `where` (predicate language, including `=~`) or `openshell.py`.

## Decisions

- Field syntax: `.name` before the pattern, plus `--field name`.
- Extra flags, all in scope: `-v`, `-F`, `-w`, `-c`, `-n`.
- `-i` and regex already work. Document and keep them; do not reimplement.
- `-c` with multiple files is one record per file (`path` + `count`), not one global total. Pipeline count is one total.
- `-n` does not add a fake `n` to pipeline records.
- Field plus files is an error, not a fallback to line text.
- Out of scope: `-A`/`-B`/`-C`, recursive `-r`, multiple fields, changing `where`, changing `parse_args`.
