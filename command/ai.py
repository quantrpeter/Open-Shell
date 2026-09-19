"""ai - ask the configured model to write and run an Open Shell pipeline."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from openshell import (
    COMMANDS,
    Json,
    Records,
    SETTINGS,
    ShellError,
    command,
    run_pipeline_records,
    ssl_context,
)

PROVIDERS = {
    "xai": "https://api.x.ai/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

DEFAULT_MODELS = {
    "xai": "grok-4.6",
    "grok": "grok-4.6",
    "openai": "gpt-4.1",
}

SAMPLE_LIMIT = 8
SKIP_COMMANDS = {"ai", "to", "json", "reload", "install", "remove"}
SECRET_NAME_RE = re.compile(r"(key|token|secret|password|passwd|authorization)", re.I)


def _setting(*names: str) -> str:
    for name in names:
        value = SETTINGS.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _ai_config() -> tuple[str, str, str, str]:
    provider = _setting("ai").lower()
    if not provider:
        raise ShellError("ai.not_configured", "no AI provider in ~/.openshell",
                         'set {"ai":"xai","ai_key":"...","ai_mode":"grok-4.6"}')
    url = PROVIDERS.get(provider)
    if url is None:
        supported = ", ".join(sorted(PROVIDERS))
        raise ShellError("ai.unknown_provider", f"unknown AI provider: {provider}",
                         f"supported providers: {supported}")
    key = _setting("ai_key", f"{provider}_key", "xai_key")
    if not key:
        raise ShellError("ai.no_key", "no AI key in ~/.openshell",
                         'set "ai_key" in ~/.openshell')
    model = _setting("ai_mode", "ai_model") or DEFAULT_MODELS.get(provider, "")
    if not model:
        raise ShellError("ai.no_model", "no AI model in ~/.openshell",
                         'set "ai_mode" in ~/.openshell')
    return provider, url, key, model


def _command_catalog() -> str:
    lines: list[str] = []
    for name in sorted(COMMANDS):
        if name in SKIP_COMMANDS:
            continue
        cmd = COMMANDS[name]
        lines.append(f"{cmd.usage}  — {cmd.summary}")
    return "\n".join(lines)


def _redact(value: Json, key: str = "") -> Json:
    if SECRET_NAME_RE.search(str(key)):
        return "***"
    if isinstance(value, dict):
        return {name: _redact(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    secret = _setting("ai_key", "xai_key")
    if secret and isinstance(value, str) and secret in value:
        return value.replace(secret, "***")
    return value


def _sample_records(incoming: list[Json]) -> list[Json]:
    return [_redact(record) for record in incoming[:SAMPLE_LIMIT]]


def _system_prompt(has_input: bool) -> str:
    mode = (
        "Input records are already flowing. Write a filter pipeline only — "
        "do not start with a source command such as ls, find, or ps."
        if has_input else
        "No input records. Write a full pipeline that starts with a source command."
    )
    return (
        "You write Open Shell pipelines. Open Shell pipes JSON records, not text.\n"
        "Reply with ONLY the pipeline on one line. No markdown, no explanation.\n"
        "Do not use ai, to, json, reload, install, or remove.\n"
        "Sort with `sort .FIELD [--desc]`. Never write sort-by.\n"
        f"{mode}\n\n"
        "Commands:\n"
        f"{_command_catalog()}"
    )


def _user_prompt(task: str, incoming: list[Json]) -> str:
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if home != os.sep and cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    payload: dict[str, Json] = {
        "task": task,
        "cwd": cwd,
        "input_count": len(incoming),
    }
    if incoming:
        payload["input_fields"] = (
            list(incoming[0].keys()) if isinstance(incoming[0], dict) else [])
        payload["input_sample"] = _sample_records(incoming)
    return json.dumps(payload, ensure_ascii=False, default=str)


def complete_chat(task: str, incoming: list[Json]) -> str:
    _provider, url, key, model = _ai_config()
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _system_prompt(bool(incoming))},
            {"role": "user", "content": _user_prompt(task, incoming)},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "openshell",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120, context=ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        err.read()  # drain, do not surface body (may echo the request)
        raise ShellError("ai.http", f"AI request failed ({err.code})",
                         "check ai, ai_key, and ai_mode in ~/.openshell") from err
    except urllib.error.URLError as err:
        raise ShellError("ai.http", f"could not reach AI provider: {err.reason}",
                         "check the network, then retry") from err
    try:
        payload = json.loads(raw.decode())
        content = payload["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as err:
        raise ShellError("ai.bad_response", "AI provider returned an unexpected payload",
                         "try again, or check ai_mode") from err
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content)
    if not isinstance(content, str) or not content.strip():
        raise ShellError("ai.bad_response", "AI provider returned an empty reply",
                         "try a more specific prompt")
    return content


def extract_pipeline(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner: list[str] = []
        for line in lines[1:]:
            if line.strip().startswith("```"):
                break
            inner.append(line)
        stripped = "\n".join(inner).strip()
    for line in stripped.splitlines():
        line = line.strip().strip("`")
        if line and not line.startswith("#"):
            return re.sub(r"\bsort-by\b", "sort", line)
    raise ShellError("ai.bad_pipeline", "AI did not return a pipeline",
                     "try a more specific prompt")


def interpret_response(text: str, incoming: list[Json]) -> list[Json]:
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return data
    if stripped.startswith("{"):
        records: list[Json] = []
        try:
            for line in stripped.splitlines():
                line = line.strip()
                if line:
                    records.append(json.loads(line))
            if records:
                return records
        except json.JSONDecodeError:
            pass
    pipeline = extract_pipeline(text)
    return run_pipeline_records(pipeline, incoming if incoming else None)


@command(
    "ai",
    "Ask the configured model to write and run a pipeline",
    "ai PROMPT …",
    source=True,
    filter=True,
)
def ai(records: Records, args: list[str]) -> Records:
    task = " ".join(args).strip()
    if not task:
        raise ShellError("arg.missing", "ai: prompt required",
                         "e.g. ai largest 3 files")
    incoming = list(records)
    text = complete_chat(task, incoming)
    yield from interpret_response(text, incoming)


@ai.help
def ai_help() -> None:
    print("ai PROMPT …")
    print("  Ask the model in ~/.openshell to write and run an Open Shell pipeline.")
    print('  Settings: "ai" (provider), "ai_key", "ai_mode" (model).')
    print("  Examples:")
    print("    ai largest 3 files")
    print("    ls | ai largest 3 files")
    print("  --help             Show this help")
