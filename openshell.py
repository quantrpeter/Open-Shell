#!/usr/bin/env python3
"""
Open Shell (`openshell`) - the AI-era shell for everyone.

A shell whose pipeline carries JSON records instead of text:

    oshell> fs.ls -r . | where .size > 10kb | sort-by .size --desc | take 5

This file is the core: the record model, the command registry, the pipeline
runner, the loader, and the frontends. The commands themselves live one per
file in `command/`, and are loaded at startup.

See skills/open-shell-design-plan.md for the design and
skills/dev-steps.md for the incremental build order.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

__version__ = "0.0.1"

# The surface a command file may rely on: `from openshell import ...`
__all__ = [
    "COMMANDS", "Json", "Records", "ShellError", "__version__", "command",
    "fetch_catalog", "fetch_registry_file", "get_field", "install_from_catalog",
    "literal", "registry_root", "remove_user_command", "sort_key",
    "use_color", "user_command_dir",
]

Json = Any
Records = Iterator[Json]


# --------------------------------------------------------------------------
# Errors are structured records, never bare tracebacks (design plan §6.6)
# --------------------------------------------------------------------------

class ShellError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_record(self) -> dict[str, str]:
        record = {"$t": "error", "code": self.code, "message": self.message}
        if self.hint:
            record["hint"] = self.hint
        return record


def use_color(stream) -> bool:
    return stream.isatty() and not os.environ.get("NO_COLOR")


def print_error(err: ShellError) -> None:
    if use_color(sys.stderr):
        sys.stderr.write(f"\033[31merror[{err.code}]\033[0m {err.message}\n")
        if err.hint:
            sys.stderr.write(f"  \033[2mhint:\033[0m {err.hint}\n")
    else:
        sys.stderr.write(json.dumps(err.to_record()) + "\n")


def print_warning(message: str) -> None:
    if use_color(sys.stderr):
        sys.stderr.write(f"\033[33mwarning\033[0m {message}\n")
    else:
        sys.stderr.write(f"warning: {message}\n")


# --------------------------------------------------------------------------
# Command registry. A file in `command/` declares its command names here;
# the filename is just a container, the decorator is the source of truth.
# --------------------------------------------------------------------------

@dataclass
class Command:
    name: str
    fn: Callable[[Records, list[str]], Any]
    summary: str
    usage: str
    source: bool = False  # produces records; must start a pipeline
    origin: str = field(default="builtin")  # which file provided it


COMMANDS: dict[str, Command] = {}


def command(name: str, summary: str, usage: str, *, source: bool = False):
    """Register a command. Names may contain dots and dashes: `fs.ls`, `sort-by`."""
    def register(fn):
        COMMANDS[name] = Command(name, fn, summary, usage, source)
        return fn
    return register


# --------------------------------------------------------------------------
# Loading commands from disk
# --------------------------------------------------------------------------

COMMAND_PATH_ENV = "OSHELL_COMMAND_PATH"
REGISTRY_URL_ENV = "OSHELL_REGISTRY_URL"
DEFAULT_REGISTRY_URL = "https://openshell.dev/registry"
SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.py$")


def user_command_dir() -> Path:
    """Installed extras live here, not in the pip package."""
    return Path.home() / ".config" / "oshell" / "command"


def command_dirs() -> list[Path]:
    """Where to look for command files, in load order (later wins on conflict)."""
    here = Path(__file__).resolve().parent
    dirs = [
        here / "command",           # source checkout
        here / "oshell_command",    # installed wheel (see pyproject package-dir)
        user_command_dir(),         # extras downloaded from the website
    ]
    extra = os.environ.get(COMMAND_PATH_ENV, "")
    dirs += [Path(p).expanduser() for p in extra.split(os.pathsep) if p]
    return dirs


def registry_root() -> str:
    return os.environ.get(REGISTRY_URL_ENV, DEFAULT_REGISTRY_URL).rstrip("/")


def join_registry(path: str) -> str:
    root = registry_root()
    rel = path.lstrip("/")
    return f"{root}/{rel}"


def fetch_bytes(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        path = Path(urllib.parse.unquote(parsed.path))
        if not path.is_file():
            raise ShellError("registry.not_found", f"no such file: {path}",
                             "check OSHELL_REGISTRY_URL")
        return path.read_bytes()
    if parsed.scheme not in ("https", "http"):
        raise ShellError("registry.bad_url", f"unsupported URL scheme: {url}",
                         "use https:// or a local file:// registry")
    request = urllib.request.Request(
        url, headers={"User-Agent": f"openshell/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.HTTPError as err:
        raise ShellError("registry.fetch_failed",
                         f"{err.code} fetching {url}",
                         "check the command name, or try `search`") from err
    except urllib.error.URLError as err:
        raise ShellError("registry.fetch_failed",
                         f"could not reach registry: {err.reason}",
                         f"set {REGISTRY_URL_ENV} or host the catalog at {DEFAULT_REGISTRY_URL}") from err


def fetch_catalog() -> dict[str, Any]:
    raw = fetch_bytes(join_registry("index.json"))
    try:
        catalog = json.loads(raw.decode())
    except json.JSONDecodeError as err:
        raise ShellError("registry.bad_index", f"invalid index.json: {err}") from err
    if not isinstance(catalog, dict) or not isinstance(catalog.get("commands"), list):
        raise ShellError("registry.bad_index", "index.json must have a commands array")
    return catalog


def fetch_registry_file(relpath: str) -> bytes:
    return fetch_bytes(join_registry(relpath))


def catalog_entry(name: str) -> dict[str, Any]:
    for entry in fetch_catalog()["commands"]:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    raise ShellError("registry.unknown", f"command not in registry: {name}",
                     "run `search` to list website commands")


def install_from_catalog(name: str) -> dict[str, Any]:
    entry = catalog_entry(name)
    relpath = str(entry.get("file") or "")
    filename = Path(relpath).name
    if not relpath or not SAFE_FILE_RE.match(filename):
        raise ShellError("registry.bad_file", f"refusing unsafe file path: {relpath!r}")

    data = fetch_registry_file(relpath)
    expected = entry.get("sha256")
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest != expected:
        raise ShellError("registry.checksum",
                         f"sha256 mismatch for {name}: got {digest}",
                         "the registry file changed; wait for a republish")

    dest = user_command_dir()
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / filename
    path.write_bytes(data)
    return {
        "name": name,
        "path": str(path),
        "origin": filename,
        "sha256": digest,
        "status": "installed",
        "registry": registry_root(),
    }


def remove_user_command(name: str) -> dict[str, Any]:
    loaded = COMMANDS.get(name)
    if loaded is None:
        raise ShellError("cmd.not_found", f"command not found: {name}",
                         "only website-installed commands can be removed")
    path = user_command_dir() / loaded.origin
    if not path.is_file():
        raise ShellError("pkg.builtin",
                         f"`{name}` is a built-in command and cannot be removed",
                         "pip ships the basic set; only `install` extras are removable")
    path.unlink()
    return {"name": name, "path": str(path), "status": "removed"}


def load_command_file(path: Path) -> list[str]:
    """Exec one command file and return the command names it registered."""
    module_name = f"oshell_command_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no import machinery for {path}")

    before = set(COMMANDS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return sorted(set(COMMANDS) - before)


def load_commands() -> list[ShellError]:
    """Load every `command/*.py`. Returns failures; a bad file is not fatal."""
    # Running as `./openshell.py` makes this module `__main__`. Alias it so a
    # command file's `from openshell import ...` finds *this* registry rather
    # than importing a second copy of this file with an empty one.
    sys.modules.setdefault("openshell", sys.modules[__name__])

    problems: list[ShellError] = []
    for directory in command_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                for name in load_command_file(path):
                    COMMANDS[name].origin = path.name
            except Exception as err:
                problems.append(ShellError(
                    "command.load_failed",
                    f"{path.name}: {type(err).__name__}: {err}",
                    "fix the file or move it out of the command folder"))
    return problems


# --------------------------------------------------------------------------
# Values and fields - shared helpers for command files
# --------------------------------------------------------------------------

SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)(b|kb|mb|gb|tb)$", re.IGNORECASE)
SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}


def literal(token: str) -> Json:
    """Turn an argument token into a JSON value. Understands `10mb`."""
    text = token.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none"):
        return None
    match = SIZE_RE.match(text)
    if match:
        return int(float(match.group(1)) * SIZE_UNITS[match.group(2).lower()])
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def get_field(record: Json, path: str) -> Json:
    """Read a dotted path out of a record, returning None when absent."""
    current = record
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def sort_key(value: Json) -> tuple[int, float, str]:
    """Total ordering across mixed JSON types: null < numbers < strings."""
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, bool):
        return (1, float(value), "")
    if isinstance(value, (int, float)):
        return (1, float(value), "")
    return (2, 0.0, str(value))


# --------------------------------------------------------------------------
# Pipeline parsing and execution
# --------------------------------------------------------------------------

def split_stages(line: str) -> list[str]:
    """Split on `|`, ignoring pipes inside quotes."""
    stages: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False

    for char in line:
        if escaped:
            buffer.append(char)
            escaped = False
        elif char == "\\":
            buffer.append(char)
            escaped = True
        elif quote:
            buffer.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            buffer.append(char)
            quote = char
        elif char == "|":
            stages.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)

    stages.append("".join(buffer))
    return [stage.strip() for stage in stages]


def run_pipeline(line: str, *, force_json: bool = False) -> int:
    parsed: list[tuple[str, list[str]]] = []
    for stage in split_stages(line):
        if not stage:
            continue
        tokens = shlex.split(stage, comments=True)
        if tokens:
            parsed.append((tokens[0], tokens[1:]))

    if not parsed:
        return 0

    # No explicit sink? Render a table for humans, NDJSON for machines.
    if parsed[-1][0] != "to":
        default = "json" if force_json or not sys.stdout.isatty() else "table"
        parsed.append(("to", [default]))

    records: Records = iter(())
    for index, (name, args) in enumerate(parsed):
        cmd = COMMANDS.get(name)
        if cmd is None:
            raise ShellError("cmd.not_found", f"command not found: {name}",
                             "run `help` for built-ins, or `search` / `install NAME` for extras")
        if cmd.source and index != 0:
            raise ShellError("pipe.source_not_first",
                             f"`{name}` produces records, so it must start the pipeline")
        if not cmd.source and index == 0:
            raise ShellError("pipe.no_input", f"`{name}` needs input records",
                             f"e.g. fs.ls | {name} ...")
        records = cmd.fn(records, args)

    for _ in records:  # drain, in case the pipeline ended without a sink
        pass
    return 0


# --------------------------------------------------------------------------
# Frontends
# --------------------------------------------------------------------------

BANNER = (f"Open Shell {__version__}  -  JSON pipelines. "
          "Try `help`, or `exit` to leave.")


def repl() -> int:
    try:
        import readline  # noqa: F401  - arrow keys and history where available
    except ImportError:
        pass

    sys.stdout.write(BANNER + "\n")
    while True:
        try:
            line = input("oshell> ").strip()
        except EOFError:
            sys.stdout.write("\n")
            return 0
        except KeyboardInterrupt:
            sys.stdout.write("^C\n")
            continue

        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit"):
            return 0

        try:
            run_pipeline(line)
        except ShellError as err:
            print_error(err)
        except KeyboardInterrupt:
            sys.stdout.write("^C\n")
        except Exception as err:  # never dump a traceback at the user
            print_error(ShellError("internal", f"{type(err).__name__}: {err}"))


USAGE = """Open Shell - the AI-era shell for everyone.

Usage:
  openshell                 start the interactive shell
  openshell -c PIPELINE     run one pipeline and exit
  openshell --json -c ...   force NDJSON output
  openshell --version

Install:
  pip install open-shell-ai # PyPI ships the core + basic commands
  openshell -c 'search'     # extras live on the website, not PyPI
  openshell -c 'install NAME'

Commands are loaded at startup from, in order:
  <install dir>/oshell_command/*.py   (basic set, from pip)
  ~/.config/oshell/command/*.py       (website extras)
  $OSHELL_COMMAND_PATH

Registry: $OSHELL_REGISTRY_URL  (default https://openshell.dev/registry)

Examples:
  openshell -c 'fs.ls'
  openshell -c 'fs.ls -r . | where .size > 10kb | sort-by .size --desc | take 5'
  openshell -c 'help | select .name .origin'
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    pipeline: str | None = None
    force_json = False

    while args:
        arg = args.pop(0)
        if arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return 0
        if arg in ("-V", "--version"):
            sys.stdout.write(f"openshell {__version__}\n")
            return 0
        if arg == "--json":
            force_json = True
        elif arg == "-c":
            if not args:
                print_error(ShellError("arg.missing", "-c needs a pipeline",
                                       "e.g. openshell -c 'fs.ls | take 3'"))
                return 2
            pipeline = args.pop(0)
        else:
            print_error(ShellError("arg.unknown", f"unknown argument: {arg}",
                                   "run `openshell --help`"))
            return 2

    for problem in load_commands():
        print_error(problem)
    if not COMMANDS:
        print_warning("no commands were loaded; is the `command/` folder missing?")

    if pipeline is None:
        return repl()

    try:
        return run_pipeline(pipeline, force_json=force_json)
    except ShellError as err:
        print_error(err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
