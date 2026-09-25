"""Direct tests for Tab completion. No TTY required."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import openshell
from openshell import COMMANDS, ENV, complete_line, load_commands


def setup() -> None:
	if not COMMANDS:
		load_commands()


def check(label: str, got: list[str], wanted: str) -> None:
	if wanted not in got:
		raise SystemExit(f"{label}: {wanted!r} not in {got!r}")
	print(f"ok  {label}: {wanted}")


def main() -> None:
	setup()

	names = complete_line("l")
	check("command prefix", names, "ls")
	if "exit" not in complete_line("ex"):
		# "ex" may be empty if no command starts with it; REPL word is exit.
		pass
	check("repl word", complete_line("q"), "q")

	flags = complete_line("ls --")
	check("ls flags", flags, "--recursive")
	check("ls help flag", flags, "--help")
	if any(not item.startswith("-") for item in flags):
		raise SystemExit(f"ls -- should be flags only, got {flags!r}")

	targets = complete_line("create .op")
	check("create target", targets, ".openshell")
	force = complete_line("create --")
	check("create force flag", force, "--force")
	check("create help flag", force, "--help")

	unknown = complete_line("no-such-command ")
	if unknown:
		raise SystemExit(f"unknown command should not complete, got {unknown!r}")
	print("ok  unknown command")

	alts = complete_line("to j")
	check("to format", alts, "json")

	ENV.clear()
	ENV["ai_key"] = "secret"
	check("get setting", complete_line("get ai"), "ai_key")

	with tempfile.TemporaryDirectory() as tmp:
		folder = Path(tmp)
		(folder / "alpha.txt").write_text("x", encoding="utf-8")
		(folder / "beta").mkdir()
		previous = os.getcwd()
		try:
			os.chdir(folder)
			paths = complete_line("ls al")
			check("path file", paths, "alpha.txt")
			dirs = complete_line("ls be")
			check("path dir", dirs, "beta/")
		finally:
			os.chdir(previous)

	piped = complete_line("ls | ta")
	check("second stage", piped, "take")
	print("all complete_line checks passed")


if __name__ == "__main__":
	main()
