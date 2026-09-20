"""ai - ask the configured model.

First in a pipeline: the model writes Open Shell commands, then they run.
Later in a pipeline: the model replies with JSON records.
"""

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
    ENV,
    ShellError,
    command,
    pipeline_index,
    run_pipeline_records,
    ssl_context,
)

PROVIDERS = {
    "xai": "https://api.x.ai/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

DEFAULT_MODELS = {
    "xai": "grok-4.6",
    "grok": "grok-4.6",
    "openai": "gpt-4.1",
    "openrouter": "openrouter/auto",
}

SAMPLE_LIMIT = 100
SKIP_COMMANDS = {"ai", "to", "json", "reload", "install", "remove"}
SECRET_NAME_RE = re.compile(r"(key|token|secret|password|passwd|authorization)", re.I)


def _setting(*names: str) -> str:
    for name in names:
        value = ENV.get(name)
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


def _plain_error_text(text: str) -> str:
    lowered = text.lower()
    if "<html" in lowered or "<!doctype" in lowered:
        if "cloudflare" in lowered or "attention required" in lowered:
            return "Cloudflare challenge page (upstream provider blocked the request)"
        return "HTML error page from upstream provider"
    return text


def _http_error_detail(err: urllib.error.HTTPError) -> str:
    try:
        raw = err.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    text = raw.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    parts: list[str] = []
    if isinstance(payload, dict):
        error = payload.get("error")
        meta: dict[str, Json] = {}
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            if message:
                parts.append(str(message))
            nested = error.get("metadata")
            if isinstance(nested, dict):
                meta = nested
        elif isinstance(error, str):
            parts.append(error)
        elif payload.get("message"):
            parts.append(str(payload["message"]))
        provider_name = meta.get("provider_name")
        nested_raw = meta.get("raw")
        if provider_name:
            parts.append(f"provider={provider_name}")
        if nested_raw:
            parts.append(_plain_error_text(str(nested_raw)))
        if not parts:
            parts.append(text)
        text = ": ".join(parts)
    else:
        text = _plain_error_text(text)
    text = str(_redact(text))
    text = " ".join(text.split())
    return text[:400]


def _command_catalog() -> str:
    lines: list[str] = []
    for name in sorted(COMMANDS):
        if name in SKIP_COMMANDS:
            continue
        cmd = COMMANDS[name]
        lines.append(f"{cmd.usage}  — {cmd.summary}")
    return "\n".join(lines)


def _system_prompt(*, as_pipeline: bool, has_input: bool) -> str:
    if as_pipeline:
        return (
            "You write Open Shell pipelines. Open Shell pipes JSON records, not text.\n"
            "Reply with ONLY the pipeline on one line. No markdown, no explanation.\n"
            "Do not use ai, to, json, reload, install, or remove.\n"
            "Sort with `sort .FIELD [--desc]`. Never write sort-by.\n"
            "No input records. Write a full pipeline that starts with a source command.\n\n"
            "Commands:\n"
            f"{_command_catalog()}"
        )
    mode = (
        "Input JSON records are provided. Answer using that data."
        if has_input else
        "No input records were provided. Answer the task directly."
    )
    return (
        "You are answering inside Open Shell, whose pipeline carries JSON records.\n"
        "Reply with JSON only. No markdown, no pipeline, no explanation.\n"
        "Prefer a JSON array of objects. A single object is also fine.\n"
        "NDJSON (one object per line) is also fine.\n"
        f"{mode}\n"
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


def complete_chat(task: str, incoming: list[Json], *, as_pipeline: bool) -> str:
    provider, url, key, model = _ai_config()
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _system_prompt(
                as_pipeline=as_pipeline, has_input=bool(incoming))},
            {"role": "user", "content": _user_prompt(task, incoming)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "openshell",
    }
    # print(json.dumps(_redact(body), ensure_ascii=False, indent=2))
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://openshell.dev"
        headers["X-Title"] = "Open Shell"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120, context=ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        detail = _http_error_detail(err)
        message = f"AI request failed ({err.code})"
        if detail:
            message = f"{message}: {detail}"
        raise ShellError("ai.http", message,
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


def _unwrap_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    inner: list[str] = []
    for line in lines[1:]:
        if line.strip().startswith("```"):
            break
        inner.append(line)
    return "\n".join(inner).strip()


def extract_pipeline(text: str) -> str:
    stripped = _unwrap_fences(text)
    for line in stripped.splitlines():
        line = line.strip().strip("`")
        if line and not line.startswith("#"):
            return re.sub(r"\bsort-by\b", "sort", line)
    raise ShellError("ai.bad_pipeline", "AI did not return a pipeline",
                     "try a more specific prompt")


def parse_answer(text: str) -> list[Json]:
    stripped = _unwrap_fences(text)
    if not stripped:
        raise ShellError("ai.bad_response", "AI provider returned an empty reply",
                         "try a more specific prompt")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
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
        raise ShellError("ai.bad_json", "AI did not return JSON",
                         "ask for a JSON array of objects") from None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return [{"answer": data}]


@command(
    "ai",
    "Ask the model: first command runs a pipeline; later stages answer as JSON",
    "ai PROMPT …",
    source=True,
    filter=True,
)
def ai(records: Records, args: list[str]) -> Records:
    task = " ".join(args).strip()
    if not task:
        raise ShellError("arg.missing", "ai: prompt required",
                         "e.g. ai largest 3 files")
    # if command is "ai provider", then show provider
    if args and args[0] == "provider":
        from openshell import ENV
        print(ENV.get("ai", "unknown"))
        return ()
    stage = pipeline_index()
    incoming = list(records)
    as_first_pipeline = stage == 1
    text = complete_chat(task, incoming, as_pipeline=as_first_pipeline)
    if as_first_pipeline:
        yield from run_pipeline_records(extract_pipeline(text))
    else:
        yield from parse_answer(text)


@ai.help
def ai_help() -> None:
    print("ai PROMPT …")
    print("  Ask the model in ~/.openshell.")
    print("  First in a pipeline: the model writes commands, then Open Shell runs them.")
    print("  Later in a pipeline: the model replies with JSON records.")
    print('  Settings: "ai" (xai|openai|openrouter), "ai_key", "ai_mode" (model).')
    print("  Examples:")
    print("")
    print("    ai provider        Show the current AI provider")
    print("    ai largest 3 files")
    print("    ls | ai largest 3 files")
    print("  --help             Show this help")
