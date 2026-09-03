# Open Shell — Design Plan

> **Status:** Draft v0.1 · Design proposal, pre-implementation
> **Project:** Open Shell (`oshell`) — the AI-era shell for everyone
> **Steward:** World Programming Society · Apache-2.0

---

## 1. Thesis

Bash pipes **text**. PowerShell pipes **.NET objects**. Open Shell pipes **JSON**.

That single choice is the whole strategy, because JSON is the only structured data format that is *simultaneously*:

- **Universal** — every language, every API, every CLI can already emit and consume it.
- **Human-readable** — you can debug a pipeline by looking at it.
- **The native tongue of LLMs** — tool calling, function schemas, and structured output are all JSON Schema today.

PowerShell's object pipeline was the right idea with the wrong substrate: its objects only exist inside .NET, so the ecosystem could never escape the runtime. Bash's text pipeline is universal but every stage re-parses fragile strings. JSON gets PowerShell's structure *and* bash's universality — and it lands exactly where the AI ecosystem already is.

**Positioning in one line:** a cross-platform, Python-extensible shell whose pipeline is JSON, which makes it the first shell that is natively legible to both humans and models.

### Why this wins for AI specifically

This is the argument to lead with, because it is a *technical* advantage, not a marketing one:

In a text shell, an AI assistant must guess at the shape of `ls -la` output, and to reason about 10,000 rows it must ingest 10,000 rows. In Open Shell, every command declares a JSON Schema, so an agent can be handed:

- the **schema** of a result (~50 tokens),
- **three sample records** (~150 tokens),
- and **aggregates** (~50 tokens),

…and then write a *new pipeline* to compute the exact answer. The model manipulates data by writing verified queries instead of eyeballing dumps. That is an order-of-magnitude difference in cost, latency, and accuracy — and it is only possible because the pipeline is typed and structured.

---

## 2. Non-goals (explicitly out of scope)

Being clear about this prevents the project from drowning.

| Not doing | Why |
|---|---|
| POSIX `sh` compliance | Running legacy `.sh` scripts is a bottomless pit. Call out to `bash`/`pwsh` instead. |
| Being your login shell in v1 | Ship as an *interactive tool* first (`oshell` from inside zsh). Login-shell duty comes after stability. |
| Reimplementing every coreutil day one | Ship ~40 high-value structured commands; wrap the rest via parsers. |
| A terminal emulator | We are the shell, not the terminal. Work well inside Ghostty/WezTerm/Windows Terminal/VS Code. |
| Beating C shells on raw startup | Aim for *imperceptible* (<120ms), not *fastest*. See §11. |

---

## 3. Naming and identity risks (resolve before launch)

Two conflicts are worth deciding on now, cheaply, rather than after a rename is expensive:

1. **`osh` is taken.** It is the binary name for [Oils for Unix](https://oils.pub) (OSH, the POSIX/bash-compatible shell, alongside YSH). Installing a second `osh` on a developer's `PATH` is a genuine collision.
   → **Decision: the binary is `oshell`.** Do not ship an `osh` symlink by default; offer it as an opt-in alias only.
2. **"Open-Shell" is taken in another domain.** [Open-Shell-Menu](https://github.com/Open-Shell/Open-Shell-Menu) (formerly Classic Shell) is a widely installed Windows Start-menu replacement. This is not a legal blocker — different product category — but it *is* an SEO and confusion problem, and it bites us in a concrete place: they already hold the winget ID `Open-Shell.Open-Shell-Menu`, on the exact platform we intend to ship to. Windows users searching winget for "open shell" will find a Start-menu skin.
   → **Mitigation:** always brand as "Open Shell (`oshell`)", own `openshell.dev`, publish under a clearly distinct winget/Scoop identifier (e.g. `WorldProgrammingSociety.OpenShell`), and use "Open Shell — the AI-era shell" as the canonical search string. Consider registering the wordmark for software/CLI goods.
3. Package/module namespace: PyPI distribution `openshell`, import package `oshell`, config dir `~/.config/oshell/`, env prefix `OSHELL_`.

---

## 4. Architecture

Six layers, each independently testable. The important property: **the engine has no dependency on the REPL**, so scripts, the daemon, the MCP server, and the interactive shell all drive the same core.

```
┌──────────────────────────────────────────────────────────────┐
│  Frontends                                                   │
│  REPL (prompt_toolkit) · oshell -c · script runner ·         │
│  oshell mcp serve · oshelld (resident daemon)                │
├──────────────────────────────────────────────────────────────┤
│  AI layer            ai.plan · ai.explain · ai.ask ·         │
│                      completion · guardrails · redaction     │
├──────────────────────────────────────────────────────────────┤
│  Language            lexer → parser → AST → static checker    │
│                      (schema-aware) → planner                 │
├──────────────────────────────────────────────────────────────┤
│  Engine              Stream runtime · lazy generators ·       │
│                      backpressure · capability enforcement ·  │
│                      run journal (record/replay)              │
├──────────────────────────────────────────────────────────────┤
│  Commands            core stdlib · registry packages ·        │
│                      external-process bridge · text parsers   │
├──────────────────────────────────────────────────────────────┤
│  Platform abstraction  fs · proc · env · pty/conpty ·        │
│                        signals · users · net                  │
└──────────────────────────────────────────────────────────────┘
```

**Language choice:** Python 3.12+ as the floor, with Python 3.14 as the "fast path" target (it is already the shipping interpreter on modern machines). Python is the right call here: the largest population of people who can write a plugin in an afternoon, the best data/AI library ecosystem, and native JSON affinity. The cost is startup latency, which §11 addresses head-on and which is a solvable engineering problem rather than a fundamental one.

---

## 5. Cross-platform strategy

The rule: **behavior is identical everywhere by default; platform-native escape hatches are explicit.**

Most "cross-platform" shells fail because they shell out to different binaries per OS. We avoid that by implementing core commands *in Python*, so `fs.ls` returns the same schema on Windows, macOS, and Linux.

| Concern | Approach |
|---|---|
| Line editing / keys / colors | `prompt_toolkit` (real Windows support, not a POSIX port) |
| Rendering | `rich` for tables/trees/JSON highlighting; degrade cleanly on dumb terminals |
| Paths | `pathlib.PurePath` internally; a `path` scalar type that carries its flavor; `/` accepted as separator on Windows input |
| Interactive child processes | `pty` on POSIX, **ConPTY** on Windows ≥10; abstracted behind `platform.spawn_pty()` |
| Signals | `SIGINT`/`SIGTERM` on POSIX ↔ `CTRL_C_EVENT`/`TerminateProcess` on Windows, behind `platform.interrupt(pid)` |
| Argument quoting | `shlex.join` on POSIX, `subprocess.list2cmdline` on Windows — never string-concatenate |
| Broken pipe | `SIGPIPE` on POSIX; explicit process termination on Windows when a downstream stage closes |
| Case sensitivity | Filesystem-case-awareness is a queryable platform capability, not an assumption |
| Feature gaps | `platform.capabilities` is itself a JSON record — commands declare required capabilities and fail with a *structured, actionable* error rather than a traceback |

**Distribution matrix (all first-class, all CI-built):**

- `uv tool install openshell` / `pipx install openshell` — the developer path
- Standalone single-file builds (PyInstaller or Nuitka) for people without Python — **this matters for the "for everyone" promise**
- Homebrew tap (macOS/Linux), winget + Scoop (Windows), `.deb`/`.rpm`, Arch AUR
- `ghcr.io/openshell/oshell` container, and a WASM/browser playground for the website (huge for adoption: "try it without installing")

---

## 6. The JSON pipeline (the core design)

### 6.1 Data model: JSON on the wire, rich types in memory

Pure JSON is missing everything a shell needs: dates, byte sizes, durations, binary, decimals, paths, 64-bit ints. If we ignore that, `where .modified > 7d ago` and `where .size > 10mb` become string-munging — and we'd have rebuilt bash with extra brackets.

The resolution: **the wire format is always valid JSON; a reserved `$`-prefixed convention carries type tags.**

```json
{"name": "report.pdf",
 "size":     {"$t": "bytes",    "v": 10485760},
 "modified": {"$t": "datetime", "v": "2026-09-03T09:18:00Z"},
 "path":     {"$t": "path",     "v": "/Users/peter/report.pdf", "flavor": "posix"}}
```

- In memory these are real Python objects (`datetime`, `Decimal`, `Path`, `bytes`), so comparison, sorting, and arithmetic just work.
- Any JSON tool can still read the stream — tags are ordinary objects, not new syntax.
- `to json --plain` flattens tags to primitives for external consumers. Fidelity when you want it, lowest common denominator when you need it.
- Tags are **optional**. A command that emits plain JSON is a valid, well-behaved command.

### 6.2 The stream envelope

A pipeline stage does not receive "a blob of bytes". It receives a `Stream`:

```python
@dataclass
class Stream:
    records: Iterator[JsonValue]   # lazy, one at a time
    meta:    StreamMeta            # O(1) per stream, not per record
    diag:    DiagChannel           # human/log messages — never pollutes data
    status:  Status                # exit code + structured error
```

`StreamMeta` carries `schema`, `source` (which command produced this), `column_order`, `units`, `run_id`, and **`trust`** (see §10.4). Keeping metadata at stream level rather than per record is what makes this cheap.

The key structural fix over bash: **data and diagnostics are separate channels.** A progress bar or a warning can never corrupt the data stream, which is the single most common source of shell-script bugs.

### 6.3 Laziness and backpressure

Everything is a generator. `fs.ls -r / | take 5` must not walk your entire disk.

- Downstream close propagates upstream via `GeneratorExit`, terminating external children.
- A stage may be *streaming* (`where`, `select`) or *blocking* (`sort-by`, `stats`); blocking stages declare it so the planner and the UI can show "collecting…".
- Long streams spill to a temp NDJSON file above a threshold instead of exhausting RAM.

### 6.4 The standard operator set

The "grammar of data" — deliberately borrowed from SQL, jq, and dataframes, because those idioms are already in people's heads:

- **Filter/shape:** `where`, `reject`, `select`, `pick`, `omit`, `rename`, `with` (computed columns), `flatten`, `expand`, `default`
- **Order/limit:** `sort-by`, `reverse`, `take`, `skip`, `first`, `last`, `uniq`, `sample`
- **Aggregate:** `group-by`, `stats` (count/sum/avg/min/max/p50/p95), `reduce`, `count`, `histogram`
- **Combine:** `join`, `union`, `zip`, `merge`, `chunk`
- **Iterate:** `each`, `par-each -j N`, `while`, `retry`
- **Convert:** `from json|ndjson|csv|tsv|yaml|toml|xml|lines|kv`, `to json|table|csv|yaml|text|md`
- **Query:** `query '.items[].name'` (jq-compatible subset), `jsonpath`
- **IO:** `open`, `save`, `http get|post`, `fs.*`, `proc.*`, `env.*`, `git.*`

### 6.5 Static checking — the differentiator

Because commands declare output schemas, the parser can check a pipeline *before it runs*:

```
> fs.ls | where .siez > 10mb
  error[E201]: field `siez` does not exist on stream from `fs.ls`
   --> line 1:20
    |
  1 | fs.ls | where .siez > 10mb
    |                ^^^^ did you mean `size`?
    |
  note: `fs.ls` emits { name: string, size: bytes, modified: datetime, ... }
```

No shell does this today. It also gives us: schema-driven tab completion of *field names* mid-pipeline, and — critically — **AI-generated pipelines that fail at compile time instead of on your filesystem** (§9.2). Checking is advisory (warn, don't block) when schemas are unknown, so dynamic cases still work.

### 6.6 Errors are records

```json
{"$t": "error", "code": "fs.permission_denied", "message": "cannot read /etc/shadow",
 "path": "/etc/shadow", "hint": "run with elevated privileges",
 "doc": "https://openshell.dev/e/fs.permission_denied"}
```

A single failed item can flow through as an error record without killing the whole pipeline (`--keep-going`), and `where .$t == "error"` becomes a legitimate handling strategy. Every error code is documented at a stable URL — which doubles as excellent grounding material for the AI layer.

---

## 7. Language sketch

Subject to an RFC; the goal is "familiar in 10 minutes to anyone who knows bash or Python."

```bash
# 1. Commands are `namespace.verb`; args stay POSIX-familiar
fs.ls -r ~/code | where .size > 10mb | sort-by .size --desc | take 5

# 2. Leading-dot field access. Unit and duration literals are first-class.
proc.list | where .cpu > 80% and .started < 1h ago | select .pid .name .cpu

# 3. `^` runs an external binary raw (text in, text out) — always explicit
^docker ps | from docker-ps | where .status == "running" | select .names .image

# 4. Variables and closures
let stale = (git.branch | where .last_commit < 90d ago)
$stale | each { |b| git.branch --delete $b.name --dry-run }

# 5. Structured error handling
try { http get https://api.example.com/users | save users.json }
catch { |e| log.error $e.message; exit 1 }

# 6. Pipelines are values — compose and reuse them
def big-files [dir: path, min: bytes = 10mb] {
    fs.ls -r $dir | where .size > $min | sort-by .size --desc
}
```

**Design rationale for the syntax choices:**

- `.field` (leading dot) makes field references unambiguous against bare-word arguments — no `$` noise, and it reads like jq.
- `^cmd` for external programs is the most important safety decision in the syntax: you can always tell by *looking* whether a line stays inside the typed world or leaves it.
- Predicates are a **restricted expression grammar**, AST-validated — not `eval()`. No imports, no attribute traversal, no dunders. Full Python is available inside `each { }` blocks in plugins, where the capability system applies.
- `namespace.verb` keeps a large community registry navigable and makes name collisions structurally impossible.

---

## 8. Interop: living in a text world

This is where most structured shells stall. The world outputs text, and telling users "rewrite your tooling" is how a shell stays a hobby project. Three mechanisms, in order of preference:

1. **Parser packages.** A registry namespace of `parsers/*` that turn known command output into JSON — `git status`, `ps`, `ip addr`, `docker ps`, `kubectl`, `systemctl`, `netstat`, `dig`. Adopt/interop with [`jc`](https://github.com/kellyjonbrazil/jc), which already covers 200+ commands, rather than duplicating that corpus. **A parser is the easiest possible first contribution** — this is our on-ramp for new contributors and should be documented as such.
2. **Native JSON detection.** Many modern CLIs already have `--json`/`-o json` (`gh`, `aws`, `kubectl`, `docker`, `terraform`, `cargo`). Ship a capability table so `^gh pr list` auto-injects `--json` and skips parsing entirely. This is where interop feels magical.
3. **Explicit conversion.** `from lines`, `from csv`, `from kv`, `from regex '...'` as the always-available fallback.

Going the other direction, JSON → text uses declared conventions (`to text`, `to lines`, `--field`) so piping into `grep` or `xargs` stays predictable. And `oshell -c '...' --json` makes Open Shell a *good citizen inside bash scripts* — an adoption wedge that doesn't require anyone to switch shells.

---

## 9. Extensibility: the command SDK

### 9.1 Authoring a command

Type hints are the single source of truth. One declaration generates the argument parser, the help text, the JSON Schema, the static-check metadata, **and the MCP tool definition**.

```python
from oshell import command, Stream, capability
from pathlib import Path
from datetime import datetime

@command("fs.big", summary="Find files larger than a threshold")
@capability("fs.read")
def big_files(
    dir: Path = Path("."),
    min: int = 10_485_760,          # rendered as a `bytes` scalar
    *,
    recursive: bool = True,
) -> Stream[FileInfo]:
    """
    Find large files.

    Examples:
        fs.big ~/Downloads --min 100mb
    """
    for p in walk(dir, recursive):
        st = p.stat()
        if st.st_size >= min:
            yield FileInfo(path=p, size=st.st_size,
                           modified=datetime.fromtimestamp(st.st_mtime))
```

Design commitments that keep the ecosystem healthy:

- **`yield`, don't `return`** — generators are the default, so laziness is the path of least resistance.
- **Output types are declared** (dataclass, `TypedDict`, or `msgspec.Struct`) → schemas are automatic, not hand-maintained and rotting.
- **Capabilities are declared in code** and cross-checked against static analysis at publish time (§10.2).
- **Docstring examples are executed as tests** in CI. Documentation that lies fails the build.

### 9.2 Local development loop

```bash
oshell pkg new my-tool          # scaffold: pyproject, manifest, tests, CI, docs
oshell pkg link ./my-tool       # editable install into the current profile
oshell pkg test                 # runs unit + docstring-example + schema-conformance tests
oshell pkg check                # lint manifest, verify declared capabilities, check API compat
oshell publish                  # sign + upload + open registry PR
```

---

## 10. The registry: how the main repo works

This is the part that determines whether Open Shell becomes an ecosystem or a curiosity. The design goal: **maximum trust with near-zero infrastructure cost**, because a volunteer-run project cannot operate a fragile service.

### 10.1 Shape: index in git, artifacts on a CDN

Precedent: crates.io's sparse index, Homebrew taps, Scoop buckets.

```
github.com/openshell/registry          # metadata ONLY — no artifacts
├── packages/
│   └── ht/http/http.json              # sharded by name prefix; all versions of one package
├── publishers/
│   └── peter.json                     # handle, GitHub identity, OIDC subject, verified flag
├── advisories/
│   └── OSHA-2026-0001.json            # security advisories, same repo → same review process
├── reserved-names.txt                 # core namespaces, trademark protection, typosquat blocks
└── .github/workflows/validate.yml     # the gate everything passes through
```

- **Git is the source of truth**: auditable history, forkable, mirrorable, no database to lose. Every version of every package is a reviewable diff.
- A **static JSON index** is generated on merge and published to `registry.openshell.dev` behind a CDN. The client only ever needs an HTTPS `GET` with ETag caching — no API server on the critical path, so `oshell install` cannot be taken down by our own uptime.
- **Artifacts** (wheels) live in GitHub Releases or R2/S3, content-addressed by SHA-256, immutable. Versions can be *yanked* but never deleted — no left-pad incidents.

A package entry:

```json
{
  "name": "http",
  "owners": ["peter", "wps-core"],
  "trust": "verified",
  "versions": [{
    "version": "1.2.0",
    "openshell": ">=1.0,<2",
    "python": ">=3.12",
    "platforms": ["linux", "darwin", "win32"],
    "artifact": "https://cdn.openshell.dev/blobs/sha256-9f2b8c…/http-1.2.0-py3-none-any.whl",
    "sha256": "9f2b8c…",
    "signature": "sigstore-bundle-url",
    "isolation": "pure",
    "capabilities": ["net"],
    "commands": [
      {"name": "http.get", "summary": "HTTP GET request",
       "input_schema": {"...": "JSON Schema 2020-12"},
       "output_schema": {"...": "JSON Schema 2020-12"}}
    ],
    "yanked": false
  }]
}
```

Command schemas are stored **in the index**, not just in the package. That means `oshell search`, static checking, and AI planning can all work against schemas *without installing anything* — you can validate a pipeline against a package you don't have. This is a small decision with large downstream leverage.

### 10.2 Submission paths

Two doors, deliberately, because casual contributors and serious maintainers need different friction:

**Door 1 — `oshell publish` (self-service, automated).**
1. Authenticate via GitHub OIDC / device flow — **no long-lived API tokens exist to leak**.
2. Client builds a wheel, computes the hash, signs with [Sigstore](https://www.sigstore.dev/) keyless signing.
3. Bot opens a PR against `openshell/registry` adding one version entry.
4. CI validates (below). All green + publisher owns the name → **auto-merge**. Otherwise a human reviews.

**Door 2 — Pull request (curated, for `verified`/`core`).** Same file format, human review, used for core namespaces and promotion between trust tiers.

**Fast path for casual sharing:** a single `.py` file with one `@command` can be installed from a URL or gist via `oshell install --from-file`. It is unsigned, runs sandboxed, and is loudly marked untrusted — but the barrier to sharing a useful 20-line command is a paste, not a publishing pipeline.

**CI gate (the same for both doors):**

- Manifest matches schema; semver monotonic; version never overwritten
- SHA-256 matches artifact; Sigstore signature verifies against the publisher's OIDC identity
- **Wheels only — sdists rejected.** This is the most important supply-chain decision we make.
- **No install-time code execution.** No `setup.py`, no postinstall hooks. The npm-postinstall attack class is structurally eliminated, not merely monitored.
- Static analysis vs. declared capabilities: imports `socket` but no `net` declared → **fail**. Capability lies are caught mechanically.
- Test matrix on ubuntu/macos/windows × supported Python versions
- SPDX license allowlist; artifact size cap; unexplained binary blobs flagged
- Typosquat distance check against existing + reserved names
- Automated review pass for known-malicious patterns (§12.11)

### 10.3 Installation and dependency isolation

Dependency hell is what kills plugin ecosystems built on a single language runtime. Two plugins wanting incompatible `httpx` versions must not be able to break the shell. Three tiers, chosen per package and recorded in the manifest:

| Tier | Mechanism | When | Cost |
|---|---|---|---|
| `pure` | In-process import; stdlib-only or vendored | Most commands | Zero overhead |
| `isolated` | Own venv + out-of-process worker, JSON-RPC over stdio | Heavy or conflicting deps (pandas, boto3) | ~30–50ms first call |
| `sandboxed` | Restricted subinterpreter (PEP 734 / `concurrent.interpreters`, Python 3.14) or container/WASM | Untrusted, AI-generated, or `--from-file` code | Varies |

Because the pipeline is JSON, the in-process and out-of-process paths are **wire-identical** — a plugin can be promoted from `pure` to `isolated` without touching a line of its code. That is a direct dividend of the JSON-pipeline decision, and it's why `isolated` is a viable default rather than a grudging fallback.

Client details: `uv` for resolution when available (fast, reproducible); `oshell.lock` with pinned hashes for reproducible team environments; `oshell audit` against `advisories/`; profiles (`oshell profile use work`) for isolated command sets; full offline mode from cache; `OSHELL_REGISTRY_URL` for mirrors and corporate proxies.

### 10.4 Trust, capabilities, and provenance

**Capabilities** are declared per package and enforced at runtime: `fs.read`, `fs.write`, `net`, `exec`, `env`, `secrets`, `clipboard`, `notify`. Install shows a plain-language consent screen:

```
Installing  http  1.2.0    (community · signed by @peter)
This package requests:
  net        make network requests
Continue? [y/N]
```

**Trust tiers**, surfaced everywhere (`search`, `info`, install prompt, and the AI planner):

- `core` — ships in the box, maintained by the core team
- `verified` — reviewed by core team, org-owned, signed
- `community` — automated checks only; installs with a visible warning

**Provenance / taint tracking** — one of the more novel pieces, and it pays off in §12.5. Every stream carries `meta.trust`. Data from the network or from an untrusted file is marked `untrusted` and stays marked as it flows downstream. Destructive commands warn when their input is tainted, and the AI layer **must never treat untrusted records as instructions**. This is a structural defense against prompt injection, expressed in the data model rather than bolted on as a filter.

### 10.5 Governance

Volunteer projects die from unclear ownership, so decide early: RFC process in `openshell/rfcs` for language and protocol changes · `CODEOWNERS` per namespace · DCO sign-off (lighter than a CLA) · documented ownership transfer requiring 2FA · 12-month abandonment → adoption process · security disclosure policy with a private channel and a 90-day window.

---

## 11. Performance: the honest risk

Python startup is the single biggest technical threat to this project. A shell that takes 400ms to print a prompt will be uninstalled regardless of how good the design is. Treat it as a **hard engineering constraint with a budget and a CI gate**, not an afterthought.

**Budget:** cold `oshell -c 'echo hi'` < 120ms · warm REPL keystroke-to-render < 16ms · simple pipeline over 10k records < 200ms.

**Tactics:**

- **Aggressive lazy imports.** `rich` and `prompt_toolkit` must not be imported for a non-interactive `-c` run. Enforce with an import-graph test.
- **No heavy startup dependencies.** Prefer `msgspec`/`orjson` over `pydantic` on the hot path (fast schema handling without the import cost).
- **CI performance gate:** `python -X importtime` and a benchmark suite run on every PR; a >10ms startup regression fails the build. This is the mechanism that actually keeps the budget — good intentions do not.
- **`oshelld` resident daemon** with a thin client, so `oshell -c` inside a loop in a bash script pays startup once. Optional, off by default, big win for scripting.
- **Free-threaded Python 3.14** for `par-each` — genuinely parallel `each` without process overhead is a compelling reason to be on a modern interpreter.
- Keep the door open to a small native launcher (Rust/Zig) later if the budget can't be met in pure Python. Design the boundary now; don't build it yet.

---

## 12. AI-ready: ideas

Ordered by "differentiating leverage", not difficulty. The first three are the flagship features that would make Open Shell genuinely novel rather than "a shell with a chatbot in it".

### 12.1 ⭐ Every command is already an MCP tool — in both directions

This is the highest-leverage idea in this document, and it is nearly free given the architecture.

Command declarations already produce JSON Schema. The current MCP specification (`2026-07-28`) requires tool `inputSchema`/`outputSchema` to be **JSON Schema 2020-12**, allows output schemas to be *unrestricted*, and lets `structuredContent` be **any JSON value** rather than only an object. A JSON-pipeline shell maps onto that with **zero translation**:

- **`oshell mcp serve`** → the entire shell, plus every installed package, becomes an MCP server. Any MCP-capable agent instantly gains hundreds of typed, documented, capability-scoped tools. Our registry effectively becomes one of the largest MCP tool catalogs in existence, and package authors get that for free without knowing MCP exists.
- **`oshell mcp add <server>`** → any MCP server is mounted as Open Shell commands, so its tools become *pipeable*: `mcp.linear.issues | where .priority == "urgent" | to table`.

Open Shell becomes the universal adapter between the CLI world and the agent world — a strategic position no other shell is architecturally positioned to take. (Implementation notes: the spec's stateless HTTP transport suits us well; do not build on the now-deprecated Roots/Sampling/Logging features; and honor the requirement not to auto-dereference external `$ref` URIs, which also applies to schemas coming from the registry.)

### 12.2 ⭐ Natural language → *verified* pipeline

Every shell-AI product today generates a string and hopes. We can do something categorically better: because commands and their schemas are known (and available from the index *without installing*, §10.1), a generated pipeline can be **statically validated before a human is even asked to approve it**.

```
> # find duplicate photos over 5mb and show total wasted space

  Proposed pipeline (validated ✓ · reads only · no network):

    fs.ls -r ~/Pictures
      | where .size > 5mb
      | with hash: (fs.hash .path)
      | group-by .hash
      | where (.items | count) > 1
      | stats wasted: (sum .size - max .size)

  [Enter] run   [e] edit   [x] explain   [d] dry-run
```

Hallucinated flags and misspelled fields are caught by the compiler, not by your filesystem. The model's output is checked against ground truth before execution — which turns "AI in the shell" from a party trick into something you can actually trust with a `--recursive`.

### 12.3 ⭐ The model writes queries, not answers

```
> proc.list | ask "what's eating my battery?"
```

The model receives the *schema* plus a handful of sample records — not 400 rows — then writes a follow-up Open Shell pipeline to compute the answer, runs it read-only, and reports **actual numbers**. No hallucinated aggregates, ~200 tokens instead of ~40,000, and it works identically on a 10-row or 10-million-row stream.

This is the concrete payoff of §1 and, in a demo, the moment where the JSON-pipeline thesis clicks for people.

### 12.4 Explain, and diagnose failures with real context

- `explain` on any pipeline, in plain language — and on a legacy bash one-liner, with an offer to translate it.
- `?!` after a failure: the AI receives the **structured** error record, the exit code, the stream schemas, cwd, and git state — not a scraped terminal buffer. Root cause plus a patch you can apply with one key.
- **Teaching mode** for the "for everyone" promise: after each command, a one-line explanation of what just happened. A `--from-bash` mode preserves existing muscle memory so nobody has to start over.

### 12.5 Guardrails, dry-run, and undo

AI in a shell is only as good as its blast radius.

- Risk is computed from **declared capabilities**, not from string-matching for `rm -rf`. `fs.write` + `--recursive` + untrusted input = high risk, confirmation required.
- **Dry-run through a copy-on-write overlay** — see exactly which files would change, as a diff, before anything happens.
- **`undo`**: reversible filesystem operations journal to a trash-backed log, so `oshell undo` genuinely works.
- AI-generated pipelines execute in a **restricted profile** by default (read-only + no network unless granted).
- **Prompt-injection defense via taint** (§10.4): content fetched from the web is data, never instruction. A tainted record cannot escalate into a command without explicit human approval.

### 12.6 Structured, semantic history

History becomes a queryable table (`command`, `cwd`, `exit`, `duration`, `git_branch`, `schema`) instead of a text file — so `history | where .exit != 0 | group-by .command | stats count` is a normal query. Add embeddings and you get `recall "that thing I did to fix the docker cert"`, which is how people actually remember their own work.

### 12.7 Agent mode with a replayable audit trail

A loop that runs read-only commands freely and pauses before writes. Because every step is a JSON record, the whole session is an **auditable, replayable, shareable transcript** (`oshell replay <run-id>`). This is what makes an agent acceptable in a production or team context, and the run journal is equally valuable for plain debugging.

### 12.8 Session → runbook → package (the self-growing ecosystem)

The loop that connects AI to the registry, and my favorite second-order idea here:

```
> oshell learn --from-run 4f2a
  Generalized 6 steps into `deploy.staging` (2 parameters).
  Created ./deploy-staging/ with tests + docs.  Publish to registry? [y/N]
```

A successful ad-hoc AI session becomes a reviewed, parameterized, *shared* command. The community's throwaway problem-solving compounds into the standard library instead of evaporating into scrollback. AI generates the raw material; humans and CI provide the quality gate.

### 12.9 Local-first, provider-agnostic, cost-aware

Completion and explanation should work offline and never leak by default:

- Small local model (Ollama / llama.cpp / LM Studio) for completion and classification — low latency, private, free.
- Cloud models (OpenAI / Anthropic / Gemini / Bedrock / Azure) for hard planning tasks, BYO key.
- **Local redaction pass** before anything leaves the machine: strip secrets, tokens, `.env` values, and home paths, with a preview of exactly what would be sent.
- A visible token/cost meter and a budget cap. Nobody should discover their shell spent $40.

### 12.10 AI-native command discovery

```
> tfstate
  Command not found. Searching registry…
    terraform.state   (verified · 12k installs)  read/query Terraform state
    tf-tools          (community · 400 installs)
  [1] install   [s] scaffold my own   [n] never mind
```

"Command not found" becomes a discovery moment — and if nothing exists, `scaffold` starts a new package. The registry gains packages precisely where users hit gaps.

### 12.11 AI on the registry side

Point the models at our own supply chain: automated first-pass review of submissions (malicious patterns, capability/manifest mismatches, obfuscation), generated docs and usage examples from schemas, generated test cases, semantic package search ("something to diff two JSON files"), and drafted release notes from diffs. This is how a volunteer core team reviews thousands of packages without burning out.

### 12.12 Smaller ideas worth keeping on the list

Error → pre-filled, redacted bug report in one keystroke · AI-suggested pipeline optimizations (`this filter should move before the sort`) · natural-language `cron`/automation authoring with the same validate-then-confirm flow · anomaly detection over piped metrics · `oshell tutor`, an interactive AI tutorial that adapts to what you already know.

---

## 13. Repository layout

```
openshell/openshell                    # the main monorepo
├── src/oshell/
│   ├── engine/          # Stream runtime, planner, capabilities, run journal
│   ├── lang/            # lexer, parser, AST, static checker
│   ├── platform/        # fs, proc, pty/conpty, signals — the cross-platform seam
│   ├── stdlib/          # core commands (fs.*, proc.*, net.*, git.*, to/from)
│   ├── sdk/             # @command, @capability, schema generation — the public API
│   ├── ai/              # planner, explain, guardrails, redaction, providers
│   ├── mcp/             # server + client bridge
│   ├── pkg/             # install, resolve, lock, publish, audit
│   └── repl/            # prompt_toolkit frontend, rendering, completion
├── tests/               # unit · golden JSON · cross-OS · fuzz (parser) · property (operators)
├── docs/                # openshell.dev source; every error code gets a page
├── examples/
└── packaging/           # PyInstaller, brew, winget, deb/rpm, container

openshell/registry       # index + advisories + publishers (§10.1)
openshell/rfcs           # language and protocol design process
openshell/packages       # core & verified first-party packages
openshell/parsers        # text→JSON parsers; the beginner on-ramp
```

**Testing posture:** golden-file JSON tests for every command (schemas are contracts, so drift must fail loudly), a full CI matrix across three OSes, fuzzing the parser, and property-based tests for stream operators (`sort | sort` is idempotent, `where` never invents records). Snapshot-test the *schemas* separately from the data — a schema change is an API change.

---

## 14. Roadmap

| Milestone | Goal | Key deliverables | Exit criteria |
|---|---|---|---|
| **M0** Spike (4–6 wk) | Prove the thesis | Engine + `Stream`, 8 commands, `where`/`select`/`sort-by`/`to table`, REPL | A demo that makes a bash user say "oh" |
| **M1** Core (2–3 mo) | A usable shell | Parser + static checker, ~40 stdlib commands, external bridge, error records, 3-OS CI, startup budget met | Daily-drivable for interactive use |
| **M2** Ecosystem (2–3 mo) | Others can extend it | SDK + `pkg new`, registry + CI gate, `publish`/`install`/`lock`, capability consent, 10 seed packages | An outside contributor publishes unaided |
| **M3** AI (2 mo) | The differentiator | `mcp serve`/`mcp add`, NL→validated pipeline, `ask`, `explain`, guardrails, local+cloud providers | §12.2 and §12.3 work reliably in a demo |
| **M4** Adoption (ongoing) | Meet people where they are | Parser corpus, single-file binaries, brew/winget, WASM playground, docs, `--from-bash` | Install to first useful pipeline < 5 min |
| **M5** 1.0 | Stability promise | Frozen language + SDK + registry schema, semver commitment, security policy, governance | Plugins written today work in 2 years |

**Sequencing rationale:** the temptation is to build the AI features first because they demo well. Resist it. AI features are only as good as the schema coverage and command breadth underneath them — §12.2 and §12.3 are *impossible* without M1's static checker and M2's schema index. Build the substrate, then the magic.

---

## 15. Open questions to resolve next

1. **Predicate expression language** — restricted-Python subset, or a small purpose-built grammar? Affects the parser, the static checker, and how easily the AI generates valid code. (Leaning: purpose-built and small, so it can be fully specified and safely generated.)
2. **Type-tag verbosity** — is `{"$t":"bytes","v":…}` acceptable in raw output, or do we need a compact form plus a schema-driven reconstruction path?
3. **Login-shell story** — do we ever support it, or is "interactive tool + script runner" the permanent, honest scope?
4. **Registry hosting** — GitHub Releases (free, simple, rate-limited) vs. Cloudflare R2 (cheap, needs an account and a funding plan)?
5. **`isolated` as the default tier?** Safer and enables per-plugin dependency freedom, but costs ~40ms per first call. Measure before deciding.
6. **AI defaults** — off until configured (privacy-respecting, weaker first impression) or a hosted free tier for onboarding (better demo, real cost and trust questions)?
7. **Windows depth** — is Windows a first-class daily driver target, or "works well via WSL"? The banner promises Windows *and* WSL, which is a meaningful engineering commitment worth sizing early.
```
