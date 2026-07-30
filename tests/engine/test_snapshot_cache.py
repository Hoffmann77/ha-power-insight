"""The snapshot cache must never outlive the snapshot it belongs to.

``PowerInsight`` is lazy and keeps no state between reads, so every sensor
entity that reads a property recomputes the whole chain behind it. A typical
install has dozens of them reading on every event, and the provenance solve runs
a max flow per source/sink pairing, so it is memoised per snapshot.

A cache like that has exactly one interesting failure mode: serving an answer
from before a reading changed. These tests pin the invalidation rather than the
speed — the results below are always compared against an engine built fresh from
the same readings, which is the definition the cache has to live up to.
"""

from __future__ import annotations

from tests.engine.scenario_framework import Adapter, Cell, State, Topology

PRICE = "sensor.grid_price"


def _topology() -> Topology:
    return Topology(
        Adapter.grid(),
        Adapter.pv("pv1", exports=True),
        Adapter.pv("pv2", exports=True),
        Adapter.battery("bat_solar", charge_from=("pv1", "pv2")),
        Adapter.battery("bat_flex"),
        Adapter.consumer("cons1"),
    )


def _engine(**readings):
    """An engine carrying exactly these readings, built from scratch."""
    return Cell(_topology(), State(price=0.30, **readings)).build_engine()


BASE = dict(grid=1500, pv1=2000, pv2=1000, bat_solar=-800, bat_flex=-400, cons1=-700)


def test_repeated_reads_within_a_snapshot_are_computed_once() -> None:
    """Nothing changed, so the second read is the first read's object."""
    engine = _engine(**BASE)

    first = engine._source_allocation
    second = engine._source_allocation

    assert first is second


def test_changing_a_reading_invalidates() -> None:
    """A new reading is a new snapshot; the old answer must not survive it."""
    engine = _engine(**BASE)
    before = engine.sink_adapters_source_shares
    assert before["bat_flex"]["grid"] > 0.0

    engine.set_value("sensor.pv1_power", 3500)

    after = engine.sink_adapters_source_shares
    assert after != before
    # ... and it is the answer a fresh engine gives for the new readings.
    assert after == _engine(**{**BASE, "pv1": 3500}).sink_adapters_source_shares


def test_writing_the_same_reading_again_does_not_invalidate() -> None:
    """Home Assistant re-reports unchanged values; that is not a new snapshot."""
    engine = _engine(**BASE)
    first = engine._source_allocation

    assert engine.set_value("sensor.pv1_power", 2000) is False

    assert engine._source_allocation is first


def test_a_reading_going_unavailable_invalidates() -> None:
    """``None`` is a change like any other, and it takes gross power with it."""
    engine = _engine(**BASE)
    assert engine.sink_adapters_source_shares != {}

    engine.set_value("sensor.pv1_power", None)

    # An unavailable inflow sensor makes gross power unknown, so provenance is
    # withdrawn rather than served stale from before the dropout.
    assert engine.gross_power is None
    assert engine.sink_adapters_source_shares == {}


def test_registering_an_adapter_invalidates() -> None:
    """The adapter set is an input too — a new device changes every result."""
    engine = _engine(**BASE)
    before = engine.sink_adapters_source_shares
    assert "bat_late" not in before

    engine.register_adapter(
        Adapter.battery("bat_late", charge_from=("pv1",)).build()
    )
    engine.set_value("sensor.bat_late_power", -300)

    assert "bat_late" in engine.sink_adapters_source_shares


def test_a_sequence_of_changes_never_serves_a_stale_answer() -> None:
    """Walk a plausible day; every step must match a fresh engine exactly."""
    engine = _engine(**BASE)
    readings = dict(BASE)

    steps = [
        ("pv1", 2500),          # sun picks up
        ("bat_solar", -1200),   # battery charges harder
        ("grid", 200),          # import falls away
        ("grid", -600),         # ... and turns into export
        ("pv2", -50),           # a string drops into standby
        ("cons1", 0),           # a load switches off entirely
        ("bat_flex", 900),      # a battery starts discharging
    ]
    for uid, value in steps:
        engine.set_value(f"sensor.{uid}_power", value)
        readings[uid] = value
        fresh = _engine(**readings)

        assert engine.sink_adapters_source_shares == fresh.sink_adapters_source_shares
        assert engine.sink_adapters_restriction_deficit == (
            fresh.sink_adapters_restriction_deficit
        )


def test_the_price_is_not_confused_for_a_power_reading() -> None:
    """A price change must not leave a power result stale, cheap though it is."""
    engine = _engine(**BASE)
    shares = engine.sink_adapters_source_shares

    assert engine.set_value(PRICE, 0.42) is True

    # Provenance does not depend on price, so the answer is unchanged -- but it
    # is recomputed rather than assumed, because the cache is dropped whole.
    assert engine.sink_adapters_source_shares == shares
