---
applyTo: "**/*.py,**/*.pyi"
---

# Python Coding Standards

Targets CPython 3.12, the version this repo pins with `uv venv -p 3.12`. Everything in the standard library up to and including 3.12 is fair game. Anything that needs 3.13 or 3.14 — t-strings, `typing.TypeIs`, deferred annotation evaluation — is out of scope until the pin moves.

## Core Principles

1. Simplicity over cleverness
2. Minimal code, maximum clarity
3. Modern syntax only, no legacy patterns
4. Annotate anything a reader would otherwise have to infer
5. Standard library first, dependency second

## Syntax

1. f-strings for all interpolation — never `%` or `str.format`: `f"Hello {name}"`
2. Builtin generics and PEP 604 unions: `list[int]`, `dict[str, int]`, `int | None`
3. Walrus for a value reused in its own condition: `if (match := pattern.search(line)):`
4. Structural pattern matching for branching on shape: `match event: case {"type": "click", "x": x}:`
5. Keyword-only parameters after `*` for anything the caller should name: `def fit(model, *, epochs=4):`
6. Positional-only before `/` when the name is an implementation detail: `def clamp(value, /, *, lo, hi):`
7. Dict merge with `|`: `settings = defaults | overrides`
8. Parenthesised context managers: `with (open(src) as f, open(dst, "w") as g):`
9. Chained comparisons instead of `and`: `if 0 <= index < len(items):`
10. Unpacking instead of indexing: `first, *rest = items`, `{**base, "extra": 1}`
11. `functools.cache` for pure memoisation, `functools.partial` for bound arguments
12. `datetime.UTC` and `zoneinfo.ZoneInfo` — never naive datetimes, never `pytz`

## Functions

1. Four-space indentation, tabs never
2. Annotate every parameter and the return type, including `-> None`
3. Immutable defaults only — never `def f(acc=[])`, use `acc: list[int] | None = None`
4. `*args` / `**kwargs` only when forwarding, and always annotated: `*args: str`, `**kwargs: object`
5. Guard clauses and early returns over nested `if` / `else`
6. Pure where possible; push I/O and mutation to the edges of the program

## Types

1. `from __future__ import annotations` as the first import of every module
2. PEP 695 type parameters and aliases: `def first[T](xs: list[T]) -> T:`, `type Vector = list[float]`
3. `Protocol` for structural interfaces; `ABC` only when subclassing is genuinely required
4. `TypedDict` for JSON and mapping shapes, `@dataclass` for records
5. `Literal[...]` or `StrEnum` for closed sets — never a bare `str` that has to be one of five things
6. `Self` for fluent and `classmethod` returns, `@override` on every override
7. `assert_never(...)` in the `case _:` arm of an exhaustive `match`
8. `Any` only at true boundaries; `# type: ignore` only with the error code and a reason

## Async

1. `asyncio.TaskGroup` for structured concurrency — siblings cancel together when one fails
2. `async with asyncio.timeout(seconds):` for deadlines instead of `asyncio.wait_for`
3. `await` at the point of call; keep a reference to every task you start or it may be collected
4. Never block the loop: no `time.sleep`, `requests`, or sync file I/O — wrap it in `asyncio.to_thread`
5. `asyncio.Runner` for a synchronous entry point that drives async code

## Collections & Iteration

1. Iterate the object — never `for i in range(len(items))`
2. `enumerate(items, start=1)` for indices, `zip(a, b, strict=True)` for parallel walks
3. Comprehensions for map and filter: `[f(x) for x in xs if x.ok]`
4. Generators for laziness, `yield from` for delegation
5. `itertools.batched(xs, n)`, `pairwise(xs)`, `groupby(xs, key=...)`, `chain.from_iterable(...)`
6. `collections.Counter`, `defaultdict(list)`, `deque(maxlen=n)`
7. `d.setdefault(k, []).append(v)` instead of get-and-assign
8. `sorted(xs, key=itemgetter(1))` instead of `key=lambda`
9. `any(...)` / `all(...)` over a generator instead of a loop accumulating a bool
10. `d.get(k, default)` instead of `k in d` followed by `d[k]`

## Strings

1. f-strings, with conversions and specs: `f"{value!r}"`, `f"{ratio:.2%}"`
2. `pathlib.Path` for every filesystem path — never `os.path` or manual `"/"` joins
3. `str.removeprefix` / `str.removesuffix` instead of slicing
4. `"".join(parts)` instead of `+=` in a loop
5. `textwrap.dedent` for multi-line literals; triple quotes for docstrings only

## Modules & Imports

1. Three blocks, one blank line apart: standard library, third-party, local
2. Absolute imports; relative `from .foo import bar` only inside a package
3. One name per line, sorted within a block (ruff `I` does this for you)
4. Declare `__all__` in packages and public modules
5. Never `from x import *`
6. `if __name__ == "__main__":` guard calling `main()`, which takes `argv` and returns an exit code

## Classes

1. `@dataclass(slots=True, frozen=True)` for records — no hand-written `__init__` that only assigns
2. `kw_only=True` when two fields are easy to transpose
3. `Protocol` for interfaces (see Types)
4. `slots=True` or `__slots__` for instances created in hot loops
5. `@property` for derived values, `@functools.cached_property` for expensive ones
6. Keep classes small; prefer functions and composition

## Error Handling

1. Raise the most specific built-in, or your own subclass of `Exception` when callers must catch it
2. Chain with `raise ConfigError(path) from err` — never lose the cause
3. Catch the narrowest exception that can occur; no bare `except:`
4. `except*` for exception groups when fan-out work fails in parallel
5. `contextlib.suppress(FileNotFoundError)` for known-benign errors, `ExitStack` for dynamic cleanup
6. Exceptions are for exceptional states, never for control flow

## Avoid

1. `global` / `nonlocal` — pass values in and return them instead
2. Mutable default arguments
3. `==` against `None`, `True`, or `False` — use `is`
4. `type(x) == T` — use `isinstance(x, T)`
5. `print` in library or service code — use logging
6. `os.path` string surgery — use `pathlib`
7. An accumulating `for` loop where a comprehension, `sum`, `any`, or `all` reads better
8. `lambda` bound to a name — use `def`
9. Wildcard imports
10. `random` for tokens, passwords, or keys — use `secrets`
11. Bare `# type: ignore` or `# noqa` without the code

## Comments

1. Comments are unwelcome in most cases (but not all)
2. Code should be self-documenting through meaningful names
3. If you need a comment, the code is too complex — simplify it
4. Acceptable: docstrings for public APIs, legal notices, complex algorithm explanations, external API peculiarities, and file header templates where necessary
5. Never: commented-out code, obvious explanations, changelog comments, TODOs without context and an owner
6. Comments should explain why, not how — the code itself should reveal the "how"

## Simplicity

Compress logic into a single expression where it stays readable: comprehensions, ternaries, `and` / `or` short-circuit, walrus. Avoid unnecessary abstraction layers, helper functions, and indirection. Single-use variables should be inlined.

Keep logic within a single level of abstraction. If you are writing an algorithm, the top level should read like a list of steps, where each step is a function call with a meaningful name. Continue that hierarchical decomposition until you reach the level of implementation details, where the real code lives rather than the structure. For example:

```python
def check_user_is_active(db, user_id: str) -> bool:
    if not is_valid_format(user_id):
        return False
    return is_user_active(fetch_user_from_db(db, user_id))
```

That should be refactored further to become:

```python
def check_user_is_active(db, user_id: str) -> bool:
    return is_valid_format(user_id) and is_user_active(fetch_user_from_db(db, user_id))
```

This final form is preferred because it has less for the reader to think about. There is no branch, but the outcome is the same: the code after `and` only executes when `is_valid_format(user_id)` is true, and otherwise the whole expression short-circuits to false.

## Structure

- At the top level sits a simple list of steps that read like English sentences; implementation details hide behind well-named functions
- Database exceptions are not propagated to the top level — they are handled inside the detail functions, so the top level only ever sees a `bool`
- No new symbols or variables are introduced that are used only once; everything is inlined

## LAWS

1. Do not use `==` against `None`, `True`, or `False` — use `is`
2. Do not write `for i in range(len(xs))` — iterate, `enumerate`, or `zip`
3. Do not use mutable default arguments
4. Do not catch broadly or swallow exceptions — catch the narrowest type and chain with `raise ... from`
5. Do not use callbacks or raw threads for concurrency — use `async` / `await` and `asyncio.TaskGroup`
6. Do not use `%` or `str.format` — use f-strings
7. Do not use `os.path` string surgery — use `pathlib`
8. Do not write comments until you have exhausted all options for making the code itself clearer

## Naming

1. `snake_case` for variables, functions, and modules; `PascalCase` for classes, `TypeAlias` values, and `Enum` members; `UPPER_SNAKE` for module-level constants
2. Use meaningful names that convey intent and come from the problem domain
3. Avoid abbreviations unless they are universally understood (e.g. `id`, `url`, `db`, `ctx`)
4. For booleans, use names that imply true/false (e.g. `is_active`, `has_permission`, `should_retry`)
5. For functions, use verb phrases that describe the action (e.g. `get_user`, `calculate_total`, `send_email`)
6. For classes, use nouns that represent the entity (e.g. `User`, `Order`, `Invoice`)
7. Use a single leading underscore only for module-private helpers; never name-mangle with `__`
8. Never use type suffixes or anything that could be read as Hungarian notation (e.g. `user_dict`, `name_str`)
9. Never use `l`, `O`, or `I` as names

## Logging

Applies to libraries, services, and scripts that are not CLIs. Logging is the standard library `logging` module, or `structlog` where a project already uses it.

**Setup — libraries create loggers, the entry point configures them:**

```python
import logging

logger = logging.getLogger(__name__)
```

**Log levels:**

| Level | When |
| --- | --- |
| `logger.debug(...)` | Operational flow: requests, events consumed/published, projections written |
| `logger.info(...)` | Lifecycle milestones: service started, connection established |
| `logger.warning(...)` | Recoverable anomalies: retries, degraded dependency, unexpected input |
| `logger.error(...)` | Errors — pass `exc_info=True`, or use `logger.exception(...)` inside an `except` block |
| `logger.critical(...)` | Unrecoverable errors before process exit |

**Lazy formatting — arguments, not f-strings, so a disabled level costs nothing:**

```python
logger.debug("event %s for shipment %s", event, shipment_id)  # correct
logger.debug(f"event {event} for shipment {shipment_id}")      # wrong
```

**Structured context — always prefer the `extra` mapping over interpolation:**

```python
logger.info("request handled", extra={"request_id": request_id, "duration_ms": elapsed})
```

**Child loggers — bind request or correlation context once:**

```python
request_log = logger.getChild(request_id)
request_log.info("handling request")
```

**Redaction — configure at logger creation, not at call sites:**

```python
SENSITIVE = ("password", "token", "authorization", "email", "phone")

def redact(record: logging.LogRecord) -> bool:
    for key in SENSITIVE:
        record.__dict__.pop(key, None)
    return True

logger.addFilter(redact)
```

**Configure once, at the process entry point:**

1. Call `logging.config.dictConfig` in `main()`, never `logging.basicConfig` in a library
2. Never attach handlers in a library module — importing it must not reconfigure the host
3. Never `print` outside CLI entry points and `--dry-run` diagnostics

**Secure logging — non-negotiable:**

1. Never log PII: names, email addresses, phone numbers, physical addresses, national IDs, dates of birth
2. Never log credentials: passwords, PINs, API keys, bearer tokens, session IDs, secrets
3. Never log payment data: card numbers, CVVs, bank accounts, sort codes
4. Log entity IDs (UUIDs) only — never the user-identifying data attached to that ID
5. Never log raw request bodies — extract and log only safe, non-sensitive fields
6. Redact sensitive fields automatically at the logger level
7. When uncertain whether a field is sensitive, do not log it

## Tooling

1. `uv` owns environments, locks, and Python versions — do not hand-roll `pip install` into a shared environment
2. `ruff` is the formatter and linter; its config is the single source of truth for line length and rules
3. A strict type checker (`basedpyright` or `pyright` in `strict` mode) runs in CI
4. `pytest` for tests, `pytest-asyncio` for async ones
