"""Self-tests for the declarative homes every engine-tier test is written in.

These guard the machinery the harnesses and reference cases rely on: devices
take their uid from the attribute they are assigned to, a miswired home or
case fails when its class is created, and ``@expect`` really compares — a
wrong expectation must fail, or every harness passes vacuously.
"""

from __future__ import annotations

import pytest

from tests.engine.home import (
    Adapter,
    Battery,
    Consumer,
    Grid,
    Home,
    Pv,
    Topology,
    expect,
)
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class _Wired(Home):
    grid = Grid(400, price=0.3)
    pv1 = Pv(600, exports=True)
    bat1 = Battery(-300, charge_from=(grid, pv1))
    plug = Consumer(None, power_from=("pv1",))

    @expect("gross_power")
    def right(self):
        return 1000

    @expect("gross_power")
    def wrong(self):
        return 999


def test_attribute_names_become_uids_and_readings():
    cell = _Wired.cell()
    assert [a.uid for a in cell.topology.adapters] == ["grid", "pv1", "bat1", "plug"]
    assert cell.state.readings == {"grid": 400, "pv1": 600, "bat1": -300, "plug": None}
    assert cell.state.price == 0.3


def test_config_and_restrictions_reach_the_adapters():
    adapters = {a.uid: a for a in _Wired.cell().topology.adapters}
    assert adapters["pv1"].config["exports_power"] is True
    assert adapters["bat1"].power_source_uids == ("grid", "pv1")
    assert adapters["plug"].power_source_uids == ("pv1",)


def test_expect_passes_on_the_right_value():
    home = _Wired()
    home.right(home.cell().build_engine())


def test_expect_fails_on_a_wrong_value():
    home = _Wired()
    with pytest.raises(AssertionError, match="gross_power") as exc:
        home.wrong(home.cell().build_engine())
    assert "expected: 999" in str(exc.value)
    assert "actual:   1000" in str(exc.value)
    assert "grid=400" in str(exc.value)


def test_a_home_needs_a_grid():
    with pytest.raises(TypeError, match="exactly one grid"):

        class _NoGrid(Home):
            pv1 = Pv(100)


def test_the_grid_is_called_grid():
    with pytest.raises(TypeError, match="grid = Grid"):

        class _Mains(Home):
            mains = Grid(100)


def test_uids_are_unique():
    with pytest.raises(ValueError, match="duplicate adapter uid"):
        Topology(Adapter.grid(), Adapter.pv("pv1"), Adapter.pv("pv1"))


def test_every_device_has_a_reading():
    with pytest.raises(TypeError, match=r"\['pv1'\] have no reading"):

        class _Unread(Home):
            grid = Grid(100)
            pv1 = Pv()


def test_a_restriction_names_a_device_of_the_same_home():
    with pytest.raises(TypeError, match="charge_from references unknown"):

        class _Stray(Home):
            grid = Grid(100)
            bat1 = Battery(-100, charge_from=("pv9",))


def test_an_unknown_config_keyword_fails_where_it_is_written():
    with pytest.raises(TypeError, match="lcos"):
        Pv(100, lcos=0.1)


def test_reserved_names_cannot_be_devices():
    with pytest.raises(TypeError, match="reserved"):

        class _Clash(Home):
            grid = Grid(100)
            price = Consumer(-50)


# ---------------------------------------------------------------------------
# Reference cases: bare devices, readings in snapshots.
# ---------------------------------------------------------------------------


class _Case(ReferenceCase):
    """A case. Shows: nothing."""

    case_id = "case"
    title = "Case"

    grid = Grid()
    pv1 = Pv(exports=True)

    class SunnyAfternoon(Snapshot):
        """Exporting."""

        grid = -300
        pv1 = 500
        price = F(1, 4)

    class PvUnavailable(Snapshot):
        """pv1 has dropped out."""

        grid = 200
        pv1 = None


def test_a_case_publishes_its_snapshots_in_order_under_snake_case_ids():
    cells = _Case.cells()
    assert [c.state.name for c in cells] == ["sunny_afternoon", "pv_unavailable"]
    assert cells[0].state.readings == {"grid": -300, "pv1": 500}
    assert cells[0].state.price == F(1, 4)
    assert cells[1].state.readings == {"grid": 200, "pv1": None}
    assert cells[1].state.price is None


def test_a_snapshot_reads_exactly_the_case_devices():
    with pytest.raises(TypeError, match=r"Missing: .*missing readings \['pv1'\]"):

        class _Short(ReferenceCase):
            grid = Grid()
            pv1 = Pv()

            class Missing(Snapshot):
                grid = 100


def test_a_case_declares_its_devices_bare():
    with pytest.raises(TypeError, match="belong in its snapshots"):

        class _Read(ReferenceCase):
            grid = Grid(100)


def test_a_case_sets_the_price_per_snapshot():
    with pytest.raises(TypeError, match="price is a reading"):

        class _Priced(ReferenceCase):
            grid = Grid(price=0.3)


def test_a_case_device_cannot_shadow_the_snapshot_api():
    with pytest.raises(TypeError, match="Snapshot already uses"):

        class _Shadow(ReferenceCase):
            grid = Grid()
            state = Consumer()


class TestTheFixtureBuildsTheHome(Home):
    grid = Grid(-200)
    pv1 = Pv(500, exports=True)

    def test_power_insight_holds_the_readings(self, power_insight):
        assert power_insight.gross_power == 500
        assert power_insight.home_base_load_power == 300
