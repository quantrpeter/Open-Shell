"""echo - emit arguments as a JSON record."""

from __future__ import annotations

from openshell import Records, command


@command("echo", "Emit arguments as a record", "echo [TEXT …]", source=True)
def echo(_input: Records, args: list[str]) -> Records:
    yield {"text": " ".join(args), "args": args}
