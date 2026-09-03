# Open Shell — Smallest Dev Steps

Build order for `openshell.py`. Each step is small, independently useful, and has a
**Done when** check you can run. Do not skip ahead: steps 7, 11 and 12 are the
differentiating features, and they are *impossible* without the substrate below them.

Section references point at `open-shell-design-plan.md`.

---

## ✅ Step 1 — Walking skeleton (DONE)

Standard library only, zero dependencies.

- `openshell.py` is the core: record model, registry, loader, pipeline runner, frontends
- `Stream` = a lazy iterator of JSON records; commands are generators
- Pipeline parser: quote-aware split on `|`, then `shlex` per stage
- Structured errors (`{"$t":"error","code":…}`), never a traceback
- Frontends: REPL and `openshell -c PIPELINE`
- Auto-sink: table on a TTY, NDJSON when piped

```bash
./openshell.py -c 'fs.ls -r . | where .size > 5kb | sort-by .size --desc | take 5'
python3 -m venv .venv && .venv/bin/pip install -e .   # gives the `openshell` command
```

**Done when:** the pipeline above prints a table; `fs.ls -r /usr | take 3` returns in
well under a second (proving laziness); `openshell --version` works from the venv.

## ✅ Step 1b — One file per command, loaded at startup (DONE)

Commands live in `command/`, one file each, discovered by path at startup — so
adding a command means adding a file, with nothing to register.

- `command/{fs_ls,where,select,sort_by,take,to,help,version}.py`
- The **decorator declares the name**, not the filename: `sort_by.py` → `sort-by`,
  `fs_ls.py` → `fs.ls`. Filenames stay valid Python identifiers; command names don't
  have to be.
- Load order: `command/` (or `oshell_command/` when installed) →
  `~/.config/oshell/command/` → `$OSHELL_COMMAND_PATH`. Later wins on conflict.
- A command file that raises is **reported and skipped**, never fatal.
- `help` reports `origin`, so `help | select .name .origin` shows which file
  provided each command.
- Command files import their SDK from `openshell` (`command`, `Records`,
  `ShellError`, `get_field`, `literal`, `sort_key`). `openshell.py` aliases itself
  into `sys.modules` as `openshell` so this resolves to the *same* registry when the
  script is run directly as `__main__`. Without that, a command file would import a
  second copy of the core with an empty registry.

**Done when:** `help | select .name .origin` lists 8 commands with their files; a
`.py` file dropped into `$OSHELL_COMMAND_PATH` adds a working command with no install
step; a deliberately broken file prints one error and the shell still runs.

**Note on packaging:** the repo folder is `command/` but it installs as
`oshell_command/` (see `pyproject.toml` `package-dir`) to avoid squatting the very
generic top-level name `command` in `site-packages`. Verify with
`pip wheel . -w /tmp/w && unzip -l /tmp/w/*.whl` after touching the layout — a wheel
missing these files yields a shell with zero commands.

## ✅ Step 1c — PyPI core + website extras (DONE)

- PyPI name is **`open-shell-ai`** (`openshell`, `oshell`, and `open-shell` are taken).
- The console script is still `openshell`.
- The wheel ships only `openshell.py` + `command/*.py` (the basic set, including
  `search` / `install` / `remove`).
- Extra commands live in `registry/` and are hosted on the website, not PyPI.
- `OSHELL_REGISTRY_URL` defaults to `https://openshell.dev/registry`. Point it at
  a local folder with `file:///abs/path/to/registry` while developing.

```bash
pip install open-shell-ai
openshell -c 'search'
openshell -c 'install count'
```

**Done when:** a clean `pip install` of the wheel has `fs.ls` and `install` but
not `count`; `install count` against the local `registry/` makes `count` work.

To publish (needs a PyPI API token; this repo has none stored):

```bash
pip install build twine
rm -rf dist
python -m build
twine upload dist/open_shell_ai-*
```

---

## Step 2 — Close the interop loop

Add `from json` (read NDJSON from stdin). ~15 lines, and it makes Open Shell usable
*inside* existing bash scripts — the adoption wedge from §8.

**Done when:** `cat data.ndjson | openshell -c 'from json | where .x > 1 | to table'`
works, and `openshell -c 'fs.ls' | jq .name` still works.

## Step 3 — Tests and CI, before more features

Pytest + golden-file JSON tests for every command, plus a GitHub Actions matrix
(ubuntu/macos/windows × 3.12/3.13/3.14). Add `-X importtime` as a startup gate now,
while it is cheap to keep (§11).

**Done when:** CI is green on all three OSes and a >10ms startup regression fails the build.

## Step 4 — Split the core, only once it hurts

Commands are already split (Step 1b); this is about the *core*. Once `openshell.py`
passes ~800–1000 lines, break it into the package layout from §13 (`engine/`, `lang/`,
`platform/`, `repl/`), with `command/` becoming `stdlib/`. Keep `openshell.py` as a
thin shim so `./openshell.py` still runs, and drop the `sys.modules` alias once the
core is a real package.

**Done when:** tests pass unchanged after the move. Resist doing this earlier — a
single core file is faster to iterate on than you expect.

## Step 5 — Rich types

Add the `{"$t":"bytes","v":…}` tag layer (§6.1): tagged JSON on the wire, real Python
objects in memory. Then `to table` can print `9.1 MB` and `2h ago`, and
`where .modified > 7d ago` becomes possible.

**Done when:** `fs.ls | to table` shows human sizes, `to json --plain` strips tags.

## Step 6 — The real command SDK

Replace `fn(records, args)` with type-hint-driven commands (§9.1): hints generate the
arg parser, the help text, **and** the JSON Schema. Docstring examples run as tests.

**Done when:** a command declares only types, and `help --schema fs.ls` emits valid
JSON Schema 2020-12.

## Step 7 — ⭐ The static checker

With schemas in hand, validate pipelines before running them (§6.5): unknown fields,
type-mismatched comparisons, `did you mean`. This is what no other shell does, and it
is the foundation for trustworthy AI generation.

**Done when:** `fs.ls | where .siez > 10mb` errors *before* touching the disk, and
tab-completion suggests field names mid-pipeline.

## Step 8 — The text world

`^cmd` for raw external processes, `from lines|csv|tsv|kv|regex`, and the `--json`
capability table for CLIs that already speak JSON (`gh`, `docker`, `kubectl`).

**Done when:** `^docker ps | from docker-ps | where .status == "running"` works.

## Step 9 — Third-party commands, safely

Folder-drop loading already works (Step 1b). What is missing is everything that makes
loading *other people's* code acceptable: discovery through Python entry points so
pip-installed packages register commands, `@capability` declarations enforced at
runtime, and the `pure` isolation tier (§10.3). `isolated` can wait.

**Done when:** a pip-installed package adds a working command via entry points, and a
package that uses `net` without declaring it is refused.

## Step 10 — The registry

`openshell/registry` repo (sharded index JSON, publishers, advisories) + the CI gate
(§10.2: wheels only, no install-time code execution, capability cross-check) +
client `install` / `lock` / `audit` / `publish`.

**Done when:** an outside contributor publishes a package and you install it by name.

## Step 11 — ⭐ MCP, both directions

`openshell mcp serve` exposes every command as an MCP tool; `openshell mcp add` mounts
an MCP server as pipeable commands (§12.1). Command schemas are already JSON Schema
2020-12, so this is mostly plumbing — the cheapest big win in the project.

**Done when:** Claude/Cursor can call `fs.ls` through your MCP server, and
`mcp.<server>.<tool> | where …` pipes.

## Step 12 — ⭐ AI that is checked, not trusted

NL → pipeline, validated by Step 7's checker before the user is asked to approve
(§12.2). Then `ask` (§12.3), `explain`, and the guardrail/dry-run layer (§12.5).

**Done when:** a natural-language request produces a pipeline that is *proven* to
reference real commands and real fields, shown for confirmation with its capability
summary, and refused when it fails the check.

---

## Working rules

1. **Every command emits records, never prints.** Only sinks (`to …`) write to stdout.
   Break this once and the pipeline stops composing.
2. **`yield`, don't `return`.** Laziness must be the default, or `take 5` on a large
   tree becomes a disaster.
3. **Errors are records** with a stable `code`, a hint, and eventually a doc URL. Those
   codes are also the AI layer's grounding material.
4. **Data and diagnostics never share a channel** (§6.2). Progress output belongs on
   stderr forever.
5. **Guard the startup budget from step 3.** No `rich`/`prompt_toolkit` import on the
   `-c` path. This is the constraint most likely to kill the project quietly.
6. **Schemas are the API.** Snapshot-test them separately; a schema change is a
   breaking change.
