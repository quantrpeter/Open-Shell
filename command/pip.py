"""pip - install Python packages that command files import.

Packages go to ~/.config/oshell/site-packages, which the shell adds to its
import path. Needed when the shell runs on a bundled Python (the GUI app).
"""

from __future__ import annotations

import sys

from openshell import Records, ShellError, command, run_external, user_site_dir


@command("pip", "Install Python packages for commands", "pip install PACKAGE … | pip list",
		 source=True)
def pip(_input: Records, args: list[str]) -> Records:
	if not args or args[0] not in ("install", "list"):
		raise ShellError("arg.bad", "pip: expected `install PACKAGE …` or `list`",
						 "e.g. pip install cryptography")
	site = user_site_dir()
	common = ["-m", "pip", "--disable-pip-version-check"]
	if args[0] == "list":
		yield from run_external(sys.executable, "pip", [*common, "list", "--path", str(site)])
		return
	if len(args) < 2:
		raise ShellError("arg.missing", "pip install: PACKAGE required",
						 "e.g. pip install cryptography")
	site.mkdir(parents=True, exist_ok=True)
	yield from run_external(
		sys.executable, "pip",
		[*common, "install", "--no-input", "--upgrade", "--target", str(site), *args[1:]])
	yield {"line": "Installed. Run `reload` to load commands that needed it.", "stream": "stdout"}
