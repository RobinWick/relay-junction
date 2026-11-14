"""Run a test file without pytest: `python3 app/test_x.py` calls every test_* function and prints a pass count.

Each test file does `try: import pytest / except ImportError: import minitest as pytest`, so this module also stands
in for the few pytest pieces the tests use: raises, skip, mark.parametrize, mark.skipif, fixture, and the built-in
fixtures tmp_path, tmp_path_factory and monkeypatch. With real pytest installed, `python3 -m pytest` still works.
"""
from __future__ import annotations

import inspect
import os
import shutil
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


class Skipped(Exception):
    pass


def skip(reason: str = "") -> None:
    raise Skipped(reason)


@contextmanager
def raises(exc: type[BaseException]):
    try:
        yield
    except exc:
        return
    raise AssertionError(f"did not raise {exc.__name__}")


def _mark(name: str):
    def make(*args, **kwargs):
        def deco(fn):
            fn.pytestmark = [*getattr(fn, "pytestmark", []), SimpleNamespace(name=name, args=args, kwargs=kwargs)]
            return fn
        return deco
    return make


mark = SimpleNamespace(parametrize=_mark("parametrize"), skipif=_mark("skipif"))


def fixture(fn=None, **_kwargs):
    if fn is None:
        return lambda f: fixture(f)
    fn._minitest_fixture = True
    return fn


class MonkeyPatch:
    _MISSING = object()

    def __init__(self) -> None:
        self._undo: list = []

    def setattr(self, target, name: str, value) -> None:
        self._undo.append(lambda old=getattr(target, name, self._MISSING): (
            delattr(target, name) if old is self._MISSING else setattr(target, name, old)))
        setattr(target, name, value)

    def setenv(self, name: str, value: str) -> None:
        self._undo.append(lambda old=os.environ.get(name): (
            os.environ.pop(name, None) if old is None else os.environ.__setitem__(name, old)))
        os.environ[name] = value

    def delenv(self, name: str, raising: bool = True) -> None:
        if name not in os.environ:
            if raising:
                raise KeyError(name)
            return
        old = os.environ.pop(name)
        self._undo.append(lambda: os.environ.__setitem__(name, old))

    def undo(self) -> None:
        while self._undo:
            self._undo.pop()()


def _raw(f):
    """The plain function behind a fixture, whether real pytest or this module decorated it."""
    if hasattr(f, "_get_wrapped_function"):
        return f._get_wrapped_function()
    return getattr(f, "__wrapped__", None) or getattr(f, "_fixture_function", None) or f


def _is_skip(e: BaseException) -> bool:
    return isinstance(e, Skipped) or type(e).__name__ == "Skipped"


def run(ns: dict) -> int:
    """Call every test_* function in the module namespace `ns`. Returns a process exit code."""
    tmp_root = Path(tempfile.mkdtemp(prefix="minitest-"))
    module_cache: dict = {}
    teardown: list = []
    counter = {"n": 0}

    def tmp_dir(prefix: str) -> Path:
        counter["n"] += 1
        d = tmp_root / f"{prefix}{counter['n']}"
        d.mkdir()
        return d

    factory = SimpleNamespace(mktemp=lambda name, numbered=True: tmp_dir(name))

    def resolve(name: str, per_test: list):
        if name == "tmp_path":
            return tmp_dir("tmp")
        if name == "tmp_path_factory":
            return factory
        if name == "monkeypatch":
            mp = MonkeyPatch()
            per_test.append(mp.undo)
            return mp
        if name in module_cache:
            if isinstance(module_cache[name], BaseException):
                raise module_cache[name]
            return module_cache[name]
        fn = _raw(ns[name])
        kwargs = {p: resolve(p, per_test) for p in inspect.signature(fn).parameters}
        try:
            value = fn(**kwargs)
            if inspect.isgenerator(value):
                gen, value = value, next(value)
                teardown.append(lambda: next(gen, None))
        except BaseException as e:  # a skip or failure in a fixture repeats for every test that uses it
            module_cache[name] = e
            raise
        module_cache[name] = value
        return value

    passed = failed = skipped = 0
    tests = [(n, f) for n, f in ns.items() if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in tests:
        marks = getattr(fn, "pytestmark", [])
        skipif = [m for m in marks if m.name == "skipif" and (m.args[0] if m.args else m.kwargs.get("condition"))]
        if skipif:
            skipped += 1
            print(f"SKIP {name}: {skipif[0].kwargs.get('reason', '')}")
            continue
        cases: list[dict] = [{}]
        for m in (m for m in marks if m.name == "parametrize"):
            argnames = [a.strip() for a in m.args[0].split(",")] if isinstance(m.args[0], str) else list(m.args[0])
            values = m.args[1]
            cases = [{**c, **dict(zip(argnames, v if len(argnames) > 1 else (v,)))} for c in cases for v in values]
        for i, case in enumerate(cases):
            label = name if len(cases) == 1 else f"{name}[{i}]"
            per_test: list = []
            try:
                kwargs = {p: case[p] if p in case else resolve(p, per_test)
                          for p in inspect.signature(fn).parameters}
                fn(**kwargs)
                passed += 1
            except BaseException as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                if _is_skip(e):
                    skipped += 1
                    print(f"SKIP {label}: {e}")
                else:
                    failed += 1
                    print(f"FAIL {label}")
                    traceback.print_exc()
            finally:
                for undo in reversed(per_test):
                    undo()
    for td in reversed(teardown):
        td()
    shutil.rmtree(tmp_root, ignore_errors=True)
    total = passed + failed + skipped
    print(f"{passed}/{total} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


def main(ns: dict) -> None:
    sys.exit(run(ns))
