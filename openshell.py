#!/usr/bin/env python3
"""
Open Shell (`openshell`) - the AI-era shell for everyone.

A shell whose pipeline carries JSON records instead of text:

    oshell> ls -r . | where .size > 10kb | sort-by .size --desc | take 5

This file is the core: the record model, the command registry, the pipeline
runner, the loader, and the frontends. The commands themselves live one per
file in `command/`, and are loaded at startup.

See skills/open-shell-design-plan.md for the design and
skills/dev-steps.md for the incremental build order.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

__version__ = "0.0.2"

# The surface a command file may rely on: `from openshell import ...`
__all__ = [
    "COMMANDS", "Json", "Records", "ShellError", "__version__", "command",
    "command_options", "expand_path", "fetch_catalog", "fetch_registry_file",
    "file_record", "format_datetime", "get_field", "human_size",
    "history_path", "install_from_catalog", "iter_file_lines", "iter_processes",
    "literal", "parse_args", "print_default_help", "registry_root",
    "reload_commands", "remove_user_command", "show_command_help", "sort_key",
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

HelpFn = Callable[..., Any]


@dataclass
class Command:
    name: str
    fn: Callable[[Records, list[str]], Any]
    summary: str
    usage: str
    source: bool = False  # produces records; must start a pipeline
    origin: str = field(default="builtin")  # which file provided it
    help_fn: HelpFn | None = None  # optional `cmd --help` printer


COMMANDS: dict[str, Command] = {}

OPTION_TOKEN_RE = re.compile(r"(?<![\w.-])(-{1,2}[A-Za-z][\w-]*)")


def command_options(usage: str) -> list[str]:
    """Flags mentioned in a usage string, in order, plus `--help`."""
    seen: set[str] = set()
    options: list[str] = []
    for token in OPTION_TOKEN_RE.findall(usage):
        if token not in seen:
            seen.add(token)
            options.append(token)
    if "--help" not in seen:
        options.append("--help")
    return options


def print_default_help(cmd: Command) -> None:
    """Default `NAME --help`: summary, usage, and every option in usage."""
    sys.stdout.write(f"{cmd.name} - {cmd.summary}\n")
    sys.stdout.write(f"\nUsage:\n  {cmd.usage}\n")
    options = command_options(cmd.usage)
    sys.stdout.write("\nOptions:\n")
    for option in options:
        suffix = "    Show this help" if option == "--help" else ""
        sys.stdout.write(f"  {option}{suffix}\n")


def show_command_help(cmd: Command) -> None:
    """Run a command's custom help function, or the default printer."""
    fn = cmd.help_fn
    if fn is None:
        print_default_help(cmd)
        return
    params = inspect.signature(fn).parameters
    result = fn(cmd) if len(params) >= 1 else fn()
    if result is None:
        return
    text = result if isinstance(result, str) else str(result)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def command(name: str, summary: str, usage: str, *, source: bool = False):
    """Register a command. Names may contain dots and dashes: `ls`, `sort-by`.

    Decorate with `@fn.help` to custom-print `NAME --help`.
    If not set, `--help` prints usage and every option in that string.
    """
    def register(fn):
        COMMANDS[name] = Command(name, fn, summary, usage, source)

        def help_decorator(custom: HelpFn) -> HelpFn:
            for registered in COMMANDS.values():
                if registered.fn is fn:
                    registered.help_fn = custom
            return custom

        fn.help = help_decorator  # type: ignore[attr-defined]
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


HISTORY_RESULT_MAX = 10_000


def history_path() -> Path:
    """Where previously run pipelines are appended, one JSON object per line."""
    override = os.environ.get("OSHELL_HISTORY")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openshell_history"


class _StdoutCapture:
    """Mirror writes to the real stdout while keeping a truncated copy."""

    def __init__(self, original, limit: int = HISTORY_RESULT_MAX) -> None:
        self._original = original
        self._limit = limit
        self._chunks: list[str] = []
        self._size = 0

    def write(self, data) -> int:
        written = self._original.write(data)
        text = data if isinstance(data, str) else str(data)
        if self._size < self._limit and text:
            piece = text[: self._limit - self._size]
            self._chunks.append(piece)
            self._size += len(piece)
        return written

    def flush(self) -> None:
        self._original.flush()

    def isatty(self) -> bool:
        return self._original.isatty()

    def __getattr__(self, name: str):
        return getattr(self._original, name)

    def captured(self) -> str:
        return "".join(self._chunks)


def append_history(line: str, result: str = "") -> None:
    """Append one JSON history record: timestamp, command, result."""
    text = line.strip()
    if not text:
        return
    if len(result) > HISTORY_RESULT_MAX:
        result = result[:HISTORY_RESULT_MAX]
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": text,
        "result": result,
    }
    try:
        path = history_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


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
    sys.modules.pop(module_name, None)
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


def reload_commands() -> tuple[list[str], list[ShellError]]:
    """Drop every registered command and load command files from disk again."""
    importlib.invalidate_caches()
    COMMANDS.clear()
    problems = load_commands()
    return sorted(COMMANDS), problems


# --------------------------------------------------------------------------
# Values and fields - shared helpers for command files
# --------------------------------------------------------------------------

SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)(b|kb|mb|gb|tb)$", re.IGNORECASE)
SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_datetime(value: datetime | float | int) -> str:
    """Format a datetime or unix timestamp as `YYYY-MM-DD HH:MM:SS`."""
    if not isinstance(value, datetime):
        value = datetime.fromtimestamp(value)
    elif value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.strftime(DATETIME_FORMAT)


def expand_path(text: str) -> Path:
    return Path(text).expanduser()


def human_size(n: int | float) -> str:
    """Render a byte count as `1.5M`, `12K`, …"""
    value = float(n)
    for unit in ("B", "K", "M", "G", "T", "P"):
        if abs(value) < 1024 or unit == "P":
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{int(n)}B"


def file_record(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "name": path.name,
        "path": str(path),
        "is_dir": path.is_dir(),
        "size": stat.st_size,
        "modified": format_datetime(stat.st_mtime),
    }


def parse_args(
    args: list[str],
    command: str,
    *,
    flags: dict[str, str] | None = None,
    valued: dict[str, str] | None = None,
) -> tuple[set[str], dict[str, str], list[str]]:
    """Parse POSIX-ish flags, including clustered shorts like `-la`.

    `flags` maps `-a`/`--all` to a canonical name in the returned set.
    `valued` maps `-n`/`--name` to a canonical name in the returned dict.
    `--name=python` is accepted for valued longs.
    """
    flags = flags or {}
    valued = valued or {}
    supported = ", ".join(sorted(set(flags) | set(valued))) or "none"
    bools: set[str] = set()
    opts: dict[str, str] = {}
    positionals: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1:])
            break
        if arg.startswith("--") and "=" in arg:
            key, value = arg.split("=", 1)
            if key not in valued:
                raise ShellError("arg.unknown", f"{command}: unknown flag {key!r}",
                                 f"supported flags: {supported}")
            opts[valued[key]] = value
            index += 1
            continue
        if arg in valued:
            if index + 1 >= len(args):
                raise ShellError("arg.missing", f"{command}: {arg} needs a value",
                                 f"supported flags: {supported}")
            opts[valued[arg]] = args[index + 1]
            index += 2
            continue
        if arg in flags:
            bools.add(flags[arg])
            index += 1
            continue
        if arg.startswith("-") and len(arg) > 2 and not arg.startswith("--"):
            token = f"-{arg[1]}"
            if token in valued:
                opts[valued[token]] = arg[2:]
                index += 1
                continue
            for char in arg[1:]:
                short = f"-{char}"
                if short in flags:
                    bools.add(flags[short])
                else:
                    raise ShellError("arg.unknown",
                                     f"{command}: unknown flag {short!r} in {arg!r}",
                                     f"supported flags: {supported}")
            index += 1
            continue
        if arg.startswith("-") and arg != "-":
            raise ShellError("arg.unknown", f"{command}: unknown flag {arg!r}",
                             f"supported flags: {supported}")
        positionals.append(arg)
        index += 1
    return bools, opts, positionals


def iter_file_lines(path: Path) -> Iterator[dict[str, Any]]:
    """Yield `{path, n, text}` records for a text file."""
    if not path.exists():
        raise ShellError("fs.not_found", f"no such path: {path}",
                         "check the path")
    if path.is_dir():
        raise ShellError("fs.is_dir", f"{path} is a directory",
                         "pass a file, or use `ls` / `find`")
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as err:
        raise ShellError("fs.read_failed", f"cannot read {path}: {err}",
                         "check the path and permissions") from err
    with handle:
        for number, line in enumerate(handle, 1):
            yield {"path": str(path), "n": number, "text": line.rstrip("\n")}


def iter_processes() -> Iterator[dict[str, Any]]:
    """Yield process records from `ps` (macOS and Linux)."""
    import subprocess

    attempts = [
        ["ps", "ax", "-o", "pid,ppid,user,%cpu,%mem,rss,state,etime,command"],
        ["ps", "ax", "-o", "pid,ppid,user,pcpu,pmem,rss,state,etime,command"],
    ]
    output = None
    for cmd in attempts:
        try:
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    if output is None:
        raise ShellError("proc.unavailable", "cannot list processes with ps",
                         "install ps, or run on macOS/Linux")

    lines = output.splitlines()
    if lines and lines[0].lstrip().lower().startswith("pid"):
        lines = lines[1:]
    for line in lines:
        parts = line.split(None, 8)
        if len(parts) < 8:
            continue
        pid, ppid, user, cpu, mem, rss, state, etime, *rest = parts
        try:
            yield {
                "pid": int(pid),
                "ppid": int(ppid),
                "user": user,
                "cpu": float(cpu),
                "mem": float(mem),
                "rss": int(rss),
                "state": state,
                "etime": etime,
                "command": rest[0] if rest else "",
            }
        except ValueError:
            continue


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

    original_stdout = sys.stdout
    capture = _StdoutCapture(original_stdout)
    error: ShellError | None = None
    try:
        sys.stdout = capture

        # No explicit sink? Render a table for humans, NDJSON for machines.
        if parsed[-1][0] != "to":
            default = "json" if force_json or not sys.stdout.isatty() else "table"
            parsed.append(("to", [default]))

        resolved: list[tuple[Command, list[str]]] = []
        for name, args in parsed:
            cmd = COMMANDS.get(name)
            if cmd is None:
                raise ShellError("cmd.not_found", f"command not found: {name}",
                                 "run `help` for built-ins, or `search` / `install NAME` for extras")
            if "--help" in args:
                show_command_help(cmd)
                return 0
            resolved.append((cmd, args))

        records: Records = iter(())
        for index, (cmd, args) in enumerate(resolved):
            if cmd.source and index != 0:
                raise ShellError("pipe.source_not_first",
                                 f"`{cmd.name}` produces records, so it must start the pipeline")
            if not cmd.source and index == 0:
                raise ShellError("pipe.no_input", f"`{cmd.name}` needs input records",
                                 f"e.g. ls | {cmd.name} ...")
            records = cmd.fn(records, args)

        for _ in records:  # drain, in case the pipeline ended without a sink
            pass
        return 0
    except ShellError as err:
        error = err
        raise
    finally:
        sys.stdout = original_stdout
        result = capture.captured()
        if not result and error is not None:
            result = json.dumps(error.to_record(), ensure_ascii=False)
        append_history(line, result)


# --------------------------------------------------------------------------
# Frontends
# --------------------------------------------------------------------------

BANNER = (f"Open Shell {__version__}  -  JSON pipelines. "
          "Try `help`, or `exit` or `q` to leave.")


def repl_cwd() -> str:
    """Directory shown in the prompt: logical `$PWD` when it still matches."""
    try:
        physical = os.getcwd()
    except OSError:
        physical = os.environ.get("PWD") or "?"
    logical = os.environ.get("PWD")
    path = physical
    if logical:
        try:
            if os.path.samefile(logical, physical):
                path = logical
        except OSError:
            pass
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if home != os.sep and path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def repl_prompt() -> str:
    return f"{repl_cwd()}>"


def _notify_terminal_cwd() -> None:
    """Tell the terminal (and VS Code) the process cwd changed."""
    if not sys.stdout.isatty() or os.environ.get("TERM") == "dumb":
        return
    try:
        cwd = os.getcwd()
    except OSError:
        return
    sys.stdout.write(f"\033]7;file://{cwd}\007")
    sys.stdout.flush()


def repl() -> int:
    try:
        import readline  # noqa: F401  - arrow keys and history where available
    except ImportError:
        pass

    try:
        os.environ.setdefault("PWD", os.getcwd())
    except OSError:
        pass

    sys.stdout.write(BANNER + "\n")
    while True:
        try:
            _notify_terminal_cwd()
            line = input(repl_prompt()).strip()
        except EOFError:
            sys.stdout.write("\n")
            return 0
        except KeyboardInterrupt:
            sys.stdout.write("^C\n")
            continue

        if not line or line.startswith("#"):
            continue
        if line in ("exit", "quit", "q"):
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
  openshell -c 'ls'
  openshell -c 'ls -r . | where .size > 10kb | sort-by .size --desc | take 5'
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
                                       "e.g. openshell -c 'ls | take 3'"))
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
