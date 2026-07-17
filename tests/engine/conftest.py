"""pytest wiring for the ``@topology`` / ``@state`` scenario framework.

``pytest_generate_tests`` parametrizes every scenario class's ``test_`` methods
over the cells (topology × state) that class declares; the fixtures below thread
the current cell into the ``power_insight`` / ``state`` / ``topology`` arguments.

Non-scenario tests in this directory are untouched — the hook no-ops unless the
test's class derives from the framework's scenario bases.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.engine.scenario_framework import generate_scenario_tests


def pytest_generate_tests(metafunc: Any) -> None:
    generate_scenario_tests(metafunc)


@pytest.fixture
def _scenario_cell(request: Any) -> Any:
    return request.param


@pytest.fixture
def power_insight(_scenario_cell: Any) -> Any:
    """A freshly built engine for the current (topology, state) cell."""
    return _scenario_cell.build_engine()


@pytest.fixture
def state(_scenario_cell: Any) -> Any:
    """The current cell's :class:`State` (for formula-style assertions)."""
    return _scenario_cell.state


@pytest.fixture
def topology(_scenario_cell: Any) -> Any:
    """The current cell's :class:`Topology`."""
    return _scenario_cell.topology
