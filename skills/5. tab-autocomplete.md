# Plan: Tab autocomplete

Add Tab completion in the interactive REPL only. Default completion comes from the command registry (names, usage flags, and a few built-in kinds). A command opts into custom completion the same way it already opts into custom `--help`: `@fn.complete`.

## Steps

1. Extend the command decorator in `openshell.py` with `fn.complete`, mirroring `fn.help`. Store the callable on `Command.complete_fn`.
2. Add a completion context and a readline completer, used only from `repl()`. Do not import or bind it on the `-c` path. On macOS libedit, set `bind ^I rl_complete` before `set_completer`, or Tab will not call the Python completer.
3. Parse the current buffer with the existing quote-aware stage split, then `shlex` the active stage. Completion is always for the last stage. A failed parse returns no matches rather than raising into the REPL.
4. Empty token or first token of a stage: complete loaded command names from `COMMANDS`, plus REPL-only words `exit`, `quit`, `q`.
5. Later tokens, no custom completer: complete flags from `command_options(cmd.usage)`, skipping nothing required beyond prefix match. Also complete these usage kinds without a custom function: `PATH`/`FILE` via filesystem prefix match (including `~`), `NAME` for `get`/`del`/`set` from `ENV` keys, and literal alternatives written as `json|table`.
6. If `complete_fn` is set, call it with the context and use its list. Signature: `(ctx) -> list[str]`. Exceptions become no matches.
7. `create` is the reference custom completer. It completes the positional target from `TARGETS` (`.openshell`, `~/.openshell`). Core merges usage flags unless the custom list already contains a `-` token, so `create` does not re-list `--force`.
8. Display is readline's own column list. Directory matches keep a trailing `/`.
9. Test the completer as a plain function: command prefix, flag prefix, `create` target prefix, path prefix, and unknown command. Do not add `prompt_toolkit`. Do not complete pipeline field names (`.size`) in this change.
10. Mention Tab in the README REPL section. Do not rewrite the design plan.

## Decisions

- Engine is stdlib `readline`, not `prompt_toolkit`.
- Custom definition matches `@fn.help`: `@fn.complete` on the command function.
- Completion context fields: `line`, `stage`, `tokens`, `word`, `command`.
- Core merges usage flags with custom results.
- Out of scope: mid-pipeline field completion, AI completion, menu UI, completing `openshell` argv outside the REPL.
