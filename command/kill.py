"""kill - terminate a process by PID."""

from __future__ import annotations

import os
import signal

from openshell import Records, ShellError, command


SIGNALS = {
    "HUP": signal.SIGHUP, "INT": signal.SIGINT, "QUIT": signal.SIGQUIT,
    "KILL": signal.SIGKILL, "TERM": signal.SIGTERM, "STOP": signal.SIGSTOP,
    "CONT": signal.SIGCONT, "USR1": signal.SIGUSR1, "USR2": signal.SIGUSR2,
}


def _parse_signal(text: str) -> int:
    raw = text.lstrip("-").upper()
    if raw.startswith("SIG"):
        raw = raw[3:]
    if raw.isdigit():
        return int(raw)
    if raw in SIGNALS:
        return int(SIGNALS[raw])
    raise ShellError("arg.bad", f"kill: unknown signal {text!r}",
                     "e.g. kill -9 1234  or  kill -TERM 1234")


@command("kill", "Terminate a process by PID", "kill [-SIGNAL] PID …", source=True)
def kill(_input: Records, args: list[str]) -> Records:
    sig = int(signal.SIGTERM)
    pids: list[int] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-s", "--signal"):
            if index + 1 >= len(args):
                raise ShellError("arg.missing", "kill: -s needs a signal",
                                 "e.g. kill -s KILL 1234")
            sig = _parse_signal(args[index + 1])
            index += 2
            continue
        if arg.startswith("-") and arg not in ("-", "--"):
            sig = _parse_signal(arg)
            index += 1
            continue
        try:
            pids.append(int(arg))
        except ValueError as err:
            raise ShellError("arg.bad", f"kill: bad pid {arg!r}",
                             "e.g. kill -9 1234") from err
        index += 1

    if not pids:
        raise ShellError("arg.missing", "kill: PID required",
                         "e.g. kill -9 1234")

    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError as err:
            raise ShellError("proc.not_found", f"no such process: {pid}",
                             "run `ps` to list PIDs") from err
        except PermissionError as err:
            raise ShellError("proc.permission", f"cannot signal {pid}: {err}",
                             "you may not own that process") from err
        except OSError as err:
            raise ShellError("proc.kill_failed", f"cannot signal {pid}: {err}",
                             "check the PID") from err
        yield {"pid": pid, "signal": sig, "killed": True}
