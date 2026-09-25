from __future__ import annotations

import json
import sys

from openshell import ENV, Json, Records, ShellError, command, use_color, format_datetime, human_size

@command("test","-","--")
def test(records: Records, args: list[str]) -> tuple[Json, ...]:
	print("test")
 
	return ()

@test.help
def ltest_help() -> None:
	print("just a test command")

@test.complete
def complete(ctx) -> list[str]:
	return ["option1", "option2", "option3"]