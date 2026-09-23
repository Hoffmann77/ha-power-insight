"""The decision log and the harnesses that enforce it stay in step.

Every modelling decision is written down once, as a ``:::note[Decision: …]``
in ``docs/dev/engine-calculations.md``, and enforced once, as a block in this
directory. These checks keep the two from drifting apart:

* every decision note says where it is pinned — ``Pinned by `TestX` ...`` —
  or says, after ``Not pinned in the engine tier:``, why it cannot be;
* every class a note names exists in ``tests/engine/manual/``;
* every block here opens its ``@state`` docstring with the decision it pins,
  so a failing test names the decision that broke.

Adding a decision note without a block, or a block without a decision, fails
here rather than going unnoticed.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import re

import pytest

from tests.engine.scenario_framework import EngineScenario

ROOT = pathlib.Path(__file__).resolve().parents[3]
LOG = ROOT / "docs" / "dev" / "engine-calculations.md"
MANUAL = pathlib.Path(__file__).resolve().parent

NOTE = re.compile(r"^:::note\[Decision: (?P<title>.+?)\]\n(?P<body>.*?)^:::$", re.M | re.S)
PINNED = re.compile(r"Pinned by `(?P<cls>Test\w+)`")
NOT_PINNED = "Not pinned in the engine tier:"


def decision_notes() -> list[tuple[str, str]]:
    return [(m["title"], m["body"]) for m in NOTE.finditer(LOG.read_text())]


def manual_classes() -> dict[str, type]:
    found = {}
    for path in sorted(MANUAL.glob("test_*.py")):
        module = importlib.import_module(f"tests.engine.manual.{path.stem}")
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, EngineScenario)
                and obj.__module__ == module.__name__
            ):
                found[name] = obj
    return found


def test_the_log_has_decisions() -> None:
    assert decision_notes(), f"no ':::note[Decision: …]' notes found in {LOG}"


@pytest.mark.parametrize(
    "title,body",
    [pytest.param(title, body, id=title) for title, body in decision_notes()],
)
def test_every_decision_says_where_it_is_pinned(title: str, body: str) -> None:
    pins = PINNED.findall(body)
    if pins:
        missing = [cls for cls in pins if cls not in manual_classes()]
        assert not missing, (
            f"Decision '{title}' is pinned by {missing}, which is not a class in "
            f"tests/engine/manual/"
        )
        return
    assert NOT_PINNED in body, (
        f"Decision '{title}' has no harness. Add a block to tests/engine/manual/ "
        f"and a 'Pinned by `TestX` in `tests/engine/manual/...`' line to its "
        f"note — or, if the engine tier cannot express it, a line starting "
        f"'{NOT_PINNED}' that says why and where it is covered instead."
    )


@pytest.mark.parametrize("name,cls", manual_classes().items(), ids=str)
def test_every_block_names_its_decision(name: str, cls: type) -> None:
    unnamed = [
        attr
        for attr, obj in vars(cls).items()
        if getattr(obj, "_scenario_role", None) == "state"
        and not inspect.cleandoc(obj.__doc__ or "").startswith("Decision")
    ]
    assert not unnamed, (
        f"{name}: the @state docstrings of {unnamed} do not start with "
        f"'Decision: …' — say which decision the block pins, so a failure "
        f"names it"
    )
