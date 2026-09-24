"""The decision log and the harnesses that enforce it stay in step.

Every modelling decision is written down once, in
``docs/dev/engine-calculations.md``, and enforced by one or more classes in
this directory — one class per decision. These checks keep the two from
drifting apart, and keep the harnesses readable:

* every ``:::note[Decision: …]`` says where it is pinned — ``Pinned by
  `TestX` in `tests/engine/manual/test_y.py``` — or says, after ``Not pinned
  in the engine tier:``, why it cannot be;
* every class a note names exists, in the module the note names;
* every class here is named in the log, so no harness pins a decision nobody
  wrote down;
* every class opens its docstring with the decision it pins, so a failing
  test names the decision that broke;
* class names are unique across the engine tier, because the log names a
  harness by its class name alone;
* every test method has a docstring saying what it checks and why.

Adding a decision note without a harness, or a harness without a decision,
fails here rather than going unnoticed.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import re

import pytest

from tests.engine.home import Home

ROOT = pathlib.Path(__file__).resolve().parents[3]
LOG = ROOT / "docs" / "dev" / "engine-calculations.md"
MANUAL = pathlib.Path(__file__).resolve().parent
ENGINE = MANUAL.parent

NOTE = re.compile(r"^:::note\[Decision: (?P<title>.+?)\]\n(?P<body>.*?)^:::$", re.M | re.S)
PINNED = re.compile(
    r"Pinned by\s+(?P<classes>(?:`Test\w+`(?:,\s*|\s+and\s+)?)+)"
    r"(?:\s+in\s+`(?P<path>tests/engine/manual/\w+\.py)`)?"
)
CLASS = re.compile(r"`(Test\w+)`")
NOT_PINNED = "Not pinned in the engine tier:"


def decision_notes() -> list[tuple[str, str]]:
    """Every ``:::note[Decision: …]`` in the log, as ``(title, body)``."""
    return [(m["title"], m["body"]) for m in NOTE.finditer(LOG.read_text())]


def collected_classes(directory: pathlib.Path, package: str) -> list[type]:
    """Every pytest-collected class defined in ``directory``'s test modules."""
    found = []
    for path in sorted(directory.rglob("test_*.py")):
        dotted = ".".join(path.relative_to(directory).with_suffix("").parts)
        module = importlib.import_module(f"{package}.{dotted}")
        found += [
            obj
            for name, obj in vars(module).items()
            if inspect.isclass(obj)
            and name.startswith("Test")
            and obj.__module__ == module.__name__
        ]
    return found


def manual_classes() -> dict[str, type]:
    """The decision harnesses: every ``Home`` class in this directory, by name."""
    return {
        cls.__name__: cls
        for cls in collected_classes(MANUAL, "tests.engine.manual")
        if issubclass(cls, Home)
    }


#: Every harness as a pytest param, identified by its class name.
HARNESSES = [pytest.param(name, cls, id=name) for name, cls in manual_classes().items()]


def test_the_log_has_decisions() -> None:
    """The decision log contains at least one decision note.

    Otherwise the checks below would pass over an empty list.
    """
    assert decision_notes(), f"no ':::note[Decision: …]' notes found in {LOG}"


@pytest.mark.parametrize(
    "title,body",
    [pytest.param(title, body, id=title) for title, body in decision_notes()],
)
def test_every_decision_says_where_it_is_pinned(title: str, body: str) -> None:
    """Every decision note names the classes that pin it, or says why none can.

    The named classes must exist, in the module the note names.
    """
    pins = [
        (cls, m["path"]) for m in PINNED.finditer(body) for cls in CLASS.findall(m["classes"])
    ]
    if pins:
        harnesses = manual_classes()
        missing = [cls for cls, _ in pins if cls not in harnesses]
        assert not missing, (
            f"Decision '{title}' is pinned by {missing}, which is not a class in "
            f"tests/engine/manual/"
        )
        misplaced = [
            f"{cls} is in {_path_of(harnesses[cls])}, not {path}"
            for cls, path in pins
            if path is not None and _path_of(harnesses[cls]) != path
        ]
        assert not misplaced, f"Decision '{title}': {misplaced}"
        return
    assert NOT_PINNED in body, (
        f"Decision '{title}' has no harness. Add a class to tests/engine/manual/ "
        f"and a 'Pinned by `TestX` in `tests/engine/manual/...`' line to its "
        f"note — or, if the engine tier cannot express it, a line starting "
        f"'{NOT_PINNED}' that says why and where it is covered instead."
    )


@pytest.mark.parametrize("name,cls", HARNESSES)
def test_every_harness_is_named_in_the_log(name: str, cls: type) -> None:
    """Every harness class is named in the decision log.

    That way the decision it pins is written down where a reader can find it.
    """
    assert f"`{name}`" in LOG.read_text(), (
        f"{name} is not named in {LOG.name}. Say which decision it pins there — "
        f"'Pinned by `{name}` in …' in its note, or beside the rule it pins."
    )


@pytest.mark.parametrize("name,cls", HARNESSES)
def test_every_harness_names_its_decision(name: str, cls: type) -> None:
    """Every harness class docstring starts with ``Decision:``.

    That way a failing test points straight at the decision that broke.
    """
    assert inspect.cleandoc(cls.__doc__ or "").startswith("Decision:"), (
        f"{name}: the class docstring does not start with 'Decision: …' — say "
        f"which decision it pins, so a failure names it"
    )


@pytest.mark.parametrize("name,cls", HARNESSES)
def test_every_harness_test_explains_itself(name: str, cls: type) -> None:
    """Every test method in a harness has a docstring.

    A first-time reader learns what it checks and why without
    reverse-engineering the numbers.
    """
    bare = [
        attr
        for attr, obj in vars(cls).items()
        if attr.startswith("test") and callable(obj) and not (obj.__doc__ or "").strip()
    ]
    assert not bare, f"{name}: test methods without a docstring: {bare}"


def test_class_names_are_unique_across_the_engine_tier() -> None:
    """No two test classes in tests/engine share a name.

    The log names a harness by its class name alone, and duplicates would make
    two unrelated failures read alike.
    """
    names = [cls.__name__ for cls in collected_classes(ENGINE, "tests.engine")]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"test classes defined more than once: {duplicates}"


def _path_of(cls: type) -> str:
    return pathlib.Path(inspect.getfile(cls)).resolve().relative_to(ROOT).as_posix()
