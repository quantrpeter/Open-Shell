"""Tests for `openshell --rpc`, the external-program fallback and Windows helpers."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_history = tempfile.TemporaryDirectory()
os.environ["OSHELL_HISTORY"] = str(Path(_history.name) / "history")

import openshell  # noqa: E402


class Client:
	"""Talks to a real `openshell --rpc` subprocess."""

	def __init__(self) -> None:
		env = dict(os.environ, PYTHONUTF8="1")
		self.proc = subprocess.Popen(
			[sys.executable, str(HERE / "openshell.py"), "--rpc"],
			stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
			text=True, encoding="utf-8", env=env, cwd=str(HERE))
		self.lines: queue.Queue[dict | None] = queue.Queue()
		self.next_id = 0
		threading.Thread(target=self._read, daemon=True).start()

	def _read(self) -> None:
		for text in self.proc.stdout:
			self.lines.put(json.loads(text))
		self.lines.put(None)

	def send(self, method: str, **params) -> int:
		self.next_id += 1
		self.proc.stdin.write(json.dumps({"id": self.next_id, "method": method, "params": params}) + "\n")
		self.proc.stdin.flush()
		return self.next_id

	def message(self, timeout: float = 10) -> dict:
		message = self.lines.get(timeout=timeout)
		assert message is not None, "server closed stdout"
		return message

	def call(self, method: str, **params) -> tuple[list[dict], dict]:
		"""Return (events, final message) for one request."""
		rid = self.send(method, **params)
		events = []
		while True:
			message = self.message()
			if message.get("id") != rid:
				continue
			if "event" in message:
				events.append(message)
			else:
				return events, message

	def close(self) -> None:
		try:
			self.proc.stdin.close()
			self.proc.wait(timeout=5)
		except Exception:
			self.proc.kill()


def records(events: list[dict]) -> list:
	return [item for event in events if event["event"] == "records" for item in event["data"]]


class RpcTests(unittest.TestCase):
	def setUp(self) -> None:
		self.client = Client()

	def tearDown(self) -> None:
		self.client.close()

	def test_info(self) -> None:
		_events, response = self.client.call("info")
		result = response["result"]
		self.assertEqual(result["protocol"], openshell.RPC_PROTOCOL)
		self.assertEqual(os.path.realpath(result["cwd"]), os.path.realpath(str(HERE)))
		self.assertIn("ls", [cmd["name"] for cmd in result["commands"]])

	def test_run_streams_records_then_result(self) -> None:
		events, response = self.client.call("run", line="ls | take 3")
		self.assertEqual(len(records(events)), 3)
		self.assertEqual(response["result"]["count"], 3)
		self.assertFalse(response["result"]["failed"])

	def test_trailing_to_is_dropped(self) -> None:
		events, _ = self.client.call("run", line="pwd | to table")
		self.assertEqual(len(records(events)), 1)

	def test_unknown_command_is_error_event(self) -> None:
		events, response = self.client.call("run", line="no-such-command-xyz")
		errors = [e for e in events if e["event"] == "error"]
		self.assertEqual(errors[0]["error"]["code"], "cmd.not_found")
		self.assertTrue(response["result"]["failed"])

	def test_unclosed_quote(self) -> None:
		events, _ = self.client.call("run", line="echo 'abc")
		self.assertEqual([e for e in events if e["event"] == "error"][0]["error"]["code"], "parse.invalid")

	def test_help_is_text_record(self) -> None:
		events, _ = self.client.call("run", line="ls --help")
		self.assertEqual(records(events)[0]["$t"], "text")

	def test_cd_changes_reported_cwd(self) -> None:
		with tempfile.TemporaryDirectory() as folder:
			target = os.path.realpath(folder)
			_, response = self.client.call("run", line=f"cd '{target}'")
			self.assertEqual(os.path.realpath(response["result"]["cwd"]), target)

	def test_complete(self) -> None:
		_, response = self.client.call("complete", line="ls | wh", cursor=7)
		self.assertEqual(response["result"]["start"], 5)
		self.assertIn("where", response["result"]["items"])

	def test_history(self) -> None:
		self.client.call("run", line="pwd")
		_, response = self.client.call("history")
		self.assertIn("pwd", response["result"]["history"])

	def test_unknown_method(self) -> None:
		_, response = self.client.call("nope")
		self.assertEqual(response["error"]["code"], "rpc.unknown_method")

	def test_shutdown_exits_with_status_zero(self) -> None:
		# A blocked stdin reader thread used to make interpreter shutdown abort (SIGABRT).
		self.client.call("shutdown")
		self.assertEqual(self.client.proc.wait(timeout=10), 0)

	def test_external_program_lines(self) -> None:
		line = f'"{sys.executable}" -c "print(\'hello\')"'
		events, response = self.client.call("run", line=line)
		self.assertEqual(records(events), [{"line": "hello", "stream": "stdout"}])
		self.assertFalse(response["result"]["failed"])

	def test_external_failure_is_error(self) -> None:
		line = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
		events, response = self.client.call("run", line=line)
		errors = [e for e in events if e["event"] == "error"]
		self.assertEqual(errors[0]["error"]["code"], "exec.exit")
		self.assertTrue(response["result"]["failed"])

	def test_soft_cancel_stops_silent_external_program(self) -> None:
		line = f'"{sys.executable}" -c "import time; print(1, flush=True); time.sleep(60)"'
		rid = self.client.send("run", line=line)
		first = self.client.message()
		self.assertEqual(first["event"], "records")
		started = time.monotonic()
		self.client.send("cancel", id=rid)
		while True:
			message = self.client.message()
			if message.get("id") == rid and "result" in message:
				break
		self.assertTrue(message["result"]["cancelled"])
		self.assertLess(time.monotonic() - started, 5)

	def test_cancel_before_start_is_honoured(self) -> None:
		slow = f'"{sys.executable}" -c "import time; time.sleep(60)"'
		first = self.client.send("run", line=slow)
		queued = self.client.send("run", line="ls")
		self.client.send("cancel", id=queued)
		self.client.send("cancel", id=first)
		finished = {}
		while len(finished) < 2:
			message = self.client.message()
			if "result" in message:
				finished[message["id"]] = message["result"]
		self.assertTrue(finished[first]["cancelled"])
		self.assertTrue(finished[queued]["cancelled"])


class InProcessTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		openshell.bootstrap()

	def test_ai_pipelines_cannot_reach_external_programs(self) -> None:
		line = f'"{sys.executable}" -c "print(1)"'
		with self.assertRaises(openshell.ShellError) as ctx:
			openshell.run_pipeline_records(line)
		self.assertEqual(ctx.exception.code, "cmd.not_found")

	def test_windows_process_rows(self) -> None:
		text = json.dumps([{"ProcessId": 4, "ParentProcessId": 0, "Name": "System",
							"WorkingSetSize": 2048, "CommandLine": None}])
		rows = list(openshell._windows_process_rows(text))
		self.assertEqual(rows[0]["pid"], 4)
		self.assertEqual(rows[0]["rss"], 2)
		self.assertEqual(rows[0]["command"], "System")
		single = json.dumps({"ProcessId": 7, "ParentProcessId": 4, "Name": "a", "WorkingSetSize": 0,
							 "CommandLine": "a.exe --x"})
		self.assertEqual(list(openshell._windows_process_rows(single))[0]["command"], "a.exe --x")

	def test_kill_signals_exist_on_every_platform(self) -> None:
		kill = sys.modules.get("oshell_command_command_kill")
		self.assertIsNotNone(kill)
		self.assertIn("KILL", kill.SIGNALS)
		self.assertIn("TERM", kill.SIGNALS)


if __name__ == "__main__":
	unittest.main()
