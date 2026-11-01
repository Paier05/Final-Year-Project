"""The Python sandbox the player's code cells (and the harness's skills) run in.

Issue #9's action loop has the player LLM write code instead of emitting one
JSON action. That code runs here, against a persistent namespace with the
episode API and the current harness's skills preloaded.

What this guards against is *accidents* by a model playing a game: an infinite
loop, an import of something with side effects, a file write. It is not a
security boundary against a determined adversary -- a restricted `exec` never
is -- and the report says so. The layers:

1. An AST filter, run before anything executes: no dunder attribute access, no
   dunder names, imports only from a small allow-list, none of the builtins
   that reach outside the namespace (`open`, `exec`, `getattr`, ...), and no
   bare `except:` (which would swallow the time limit and the action cap).
2. A whitelist of builtins. `__import__` is replaced by one that enforces the
   same allow-list at run time.
3. A per-cell time limit enforced with `sys.settrace`, which is per-thread, so
   episodes running in parallel threads each get their own clock.

`random` and `time` are deliberately not importable: cells must be
deterministic so that Validate can replay them exactly.
"""

from __future__ import annotations

import ast
import builtins
import collections
import functools
import heapq
import io
import itertools
import math
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

# Modules whose public attributes do not lead back to `sys`/`os`. `re` and
# `statistics` were dropped from this list because they do (`re.enum.sys`,
# `statistics.sys`).
ALLOWED_IMPORTS = frozenset(
    {"math", "collections", "itertools", "functools", "heapq", "numpy"}
)

# Attribute names that reach frames, globals, the filesystem or other modules.
# Anything starting with "_" is refused as well, which covers dunders and the
# private module aliases (`collections._sys`).
FORBIDDEN_ATTRS = frozenset(
    {
        "gi_frame", "gi_code", "gi_yieldfrom", "cr_frame", "cr_code", "ag_frame",
        "ag_code", "f_globals", "f_locals", "f_builtins", "f_back", "f_code",
        "tb_frame", "tb_next", "co_code", "sys", "os", "builtins", "modules",
        "subprocess", "system", "ctypeslib", "ctypes", "lib", "testing", "f2py",
        "tofile", "fromfile", "save", "savez", "savez_compressed", "savetxt",
        "load", "loadtxt", "genfromtxt", "memmap", "inspect",
        # Unseeded randomness would make cells impossible to replay exactly.
        "random",
    }
)

FORBIDDEN_NAMES = frozenset(
    {
        "open", "exec", "eval", "compile", "__import__", "globals", "locals",
        "vars", "getattr", "setattr", "delattr", "input", "breakpoint", "exit",
        "quit", "help", "memoryview", "classmethod", "staticmethod", "property",
        "super", "BaseException",
    }
)

_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "hash", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next", "object", "ord", "chr",
    "pow", "range", "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "zip", "callable", "hex", "bin",
    "Exception", "ValueError", "KeyError", "IndexError", "TypeError",
    "RuntimeError", "StopIteration", "AssertionError", "ZeroDivisionError",
    "ArithmeticError", "LookupError", "NameError", "AttributeError",
    "NotImplementedError", "True", "False", "None",
)

MAX_STDOUT_CHARS = 4000


class SandboxViolation(ValueError):
    """The code was rejected before running: it breaks a sandbox rule."""


class SandboxTimeout(BaseException):
    """A cell exceeded its time limit.

    BaseException, not Exception, so model code catching `Exception` cannot
    swallow it and keep looping. Bare `except:` is rejected by the AST filter
    for the same reason.
    """


class TurnOver(BaseException):
    """Raised by the episode API to stop a cell: action cap, budget, or a clear.

    Not an error. It ends the cell cleanly and the harness reports why.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_source(source: str) -> ast.Module:
    """Parse `source` and enforce the sandbox rules. Raises SandboxViolation."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise SandboxViolation(f"SyntaxError: {error.msg} (line {error.lineno})") from error

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRS
        ):
            raise SandboxViolation(
                f"line {node.lineno}: attribute '.{node.attr}' is not allowed in the sandbox"
            )
        if isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or node.id.startswith("__"):
                raise SandboxViolation(
                    f"line {node.lineno}: '{node.id}' is not available in the sandbox"
                )
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                if name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise SandboxViolation(
                        f"line {node.lineno}: import of '{name}' is not allowed; "
                        f"allowed: {', '.join(sorted(ALLOWED_IMPORTS))}"
                    )
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            raise SandboxViolation(
                f"line {node.lineno}: bare 'except:' is not allowed; catch Exception"
            )
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            # Allowed, but only for plain names, which ast guarantees.
            continue
    return tree


def _guarded_import(name: str, globals_=None, locals_=None, fromlist=(), level=0):
    if level != 0 or name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import of '{name}' is not allowed in the sandbox")
    return builtins.__import__(name, globals_, locals_, fromlist, level)


def safe_builtins(print_fn: Callable[..., None]) -> dict[str, Any]:
    table = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
    table["print"] = print_fn
    table["__import__"] = _guarded_import
    # Needed for `class` statements to work at all.
    table["__build_class__"] = builtins.__build_class__
    return table


@dataclass
class CellResult:
    stdout: str = ""
    error: str | None = None
    timed_out: bool = False
    stopped_by: str | None = None  # TurnOver reason, if the API ended the cell
    violation: bool = False


@dataclass
class Sandbox:
    """A persistent namespace plus a guarded `run(code)`.

    `preload` is the episode API (action, grid, ...); skills are added with
    `load_skill_source`. Everything a cell defines persists to later cells.
    """

    preload: dict[str, Any] = field(default_factory=dict)
    time_limit_s: float = 10.0
    namespace: dict[str, Any] = field(default_factory=dict)
    _buffer: io.StringIO = field(default_factory=io.StringIO)

    def __post_init__(self) -> None:
        self.namespace = {
            "__builtins__": safe_builtins(self._print),
            "__name__": "sandbox",
            "np": np,
            "math": math,
            "collections": collections,
            "itertools": itertools,
            "functools": functools,
            "heapq": heapq,
            "notes": "",
        }
        self.namespace.update(self.preload)

    def _print(self, *args: Any, sep: str = " ", end: str = "\n", **_: Any) -> None:
        self._buffer.write(sep.join(str(a) for a in args) + end)

    def _execute(self, tree: ast.Module, filename: str) -> None:
        code = compile(tree, filename, "exec")
        deadline = time.monotonic() + self.time_limit_s
        counter = [0]

        def tracer(frame, event, arg):
            counter[0] += 1
            # Checking the clock on every event is needlessly slow.
            if counter[0] % 256 == 0 and time.monotonic() > deadline:
                raise SandboxTimeout(f"cell exceeded {self.time_limit_s:.0f}s")
            return tracer

        previous = sys.gettrace()
        sys.settrace(tracer)
        try:
            exec(code, self.namespace)  # noqa: S102 - guarded by check_source
        finally:
            sys.settrace(previous)

    def run(self, source: str, filename: str = "<cell>") -> CellResult:
        result = CellResult()
        self._buffer = io.StringIO()
        try:
            tree = check_source(source)
        except SandboxViolation as error:
            result.error = f"SandboxViolation: {error}"
            result.violation = True
            return result

        try:
            with redirect_stdout(self._buffer):
                self._execute(tree, filename)
        except TurnOver as stop:
            result.stopped_by = stop.reason
        except SandboxTimeout as error:
            result.timed_out = True
            result.error = f"Timeout: {error}"
        except Exception as error:  # noqa: BLE001 - the model's bug, reported back
            result.error = _format_error(error, filename)
        output = self._buffer.getvalue()
        if len(output) > MAX_STDOUT_CHARS:
            output = output[:MAX_STDOUT_CHARS] + f"\n... (output truncated at {MAX_STDOUT_CHARS} chars)"
        result.stdout = output
        return result

    def load_skill_source(self, name: str, source: str) -> None:
        """Exec a skill's source into the namespace. Raises on any failure."""
        tree = check_source(source)
        self._execute(tree, f"<skill {name}>")
        if not callable(self.namespace.get(name)):
            raise SandboxViolation(f"skill source does not define a function named {name!r}")


def _format_error(error: Exception, filename: str) -> str:
    """`Type: message (line N)`, with the line number inside the cell when known."""
    line = None
    tb = error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == filename:
            line = tb.tb_lineno
        tb = tb.tb_next
    where = f" (line {line})" if line else ""
    return f"{type(error).__name__}: {error}{where}"


# ---------------------------------------------------------------------------
# Static analysis used by Analyze and Validate
# ---------------------------------------------------------------------------


def _strip_docstring(node: ast.FunctionDef) -> ast.FunctionDef:
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), ast.Constant
    ) and isinstance(body[0].value.value, str):
        body = body[1:] or [ast.Pass()]
    clone = ast.FunctionDef(
        name="_",
        args=node.args,
        body=body,
        decorator_list=[],
        returns=None,
        type_comment=None,
        type_params=[],
    )
    return ast.fix_missing_locations(clone)


def function_key(node: ast.FunctionDef) -> str:
    """Name- and docstring-independent identity of a function body.

    Two helpers the model wrote with different names but the same code get the
    same key, which is what makes merge candidates detectable.
    """
    return ast.unparse(_strip_docstring(node))


def defined_functions(source: str) -> list[dict[str, Any]]:
    """Top-level functions defined in a cell: name, key, source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.append(
                {
                    "name": node.name,
                    "key": function_key(node),
                    "source": ast.unparse(node),
                    "n_lines": len(ast.unparse(node).splitlines()),
                }
            )
    return out


def called_names(source: str) -> collections.Counter:
    """How many times each bare name is called in `source`."""
    counts: collections.Counter = collections.Counter()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return counts
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            counts[node.func.id] += 1
    return counts


def strip_function_defs(source: str, name: str, key: str | None = None) -> str:
    """Remove top-level `def name` from a cell (only the variant `key`, if given)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    kept = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == name
            and (key is None or function_key(node) == key)
        )
    ]
    if len(kept) == len(tree.body):
        return source
    tree.body = kept or [ast.Pass()]
    return ast.unparse(tree)
