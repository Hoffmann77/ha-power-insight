"""Tests for the carried-over history (``history.py``).

The expected values are the worked examples in
docs/dev/carried-over-history.md, derived by hand from the engine's credit
rules: PV → home earns the tariff, PV → battery earns the PV its feed-in rate
(the battery pays it, docs/dev/stored-energy-pricing.md), the battery earns
the tariff when it discharges, and levelized figures subtract the energy's
current LCOE / LCOS.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.power_insight.history import (
    BATTERY,
    ERROR_CHARGING_NOT_COVERED,
    ERROR_DOES_NOT_BALANCE,
    ERROR_EXPORT_COMPENSATION_NOT_SPLITTABLE,
    ERROR_FED_IN_EXCEEDS_HOME,
    ERROR_FED_IN_EXCEEDS_OUTPUT,
    ERROR_FED_IN_EXCEEDS_PRODUCTION,
    ERROR_FED_IN_REQUIRED,
    ERROR_GRID_CHARGED_EXCEEDS_CHARGED,
    ERROR_PARTIAL_ENERGY,
    ERROR_SAVINGS_NOT_SPLITTABLE,
    ERROR_TARIFF_REQUIRED,
    MISSING_ENERGY,
    MISSING_FEED_IN_TARIFF,
    MISSING_PRICE,
    MISSING_TARIFF,
    MISSING_WAITING,
    PV_SYSTEM,
    DeviceInputs,
    HomeInputs,
    Problem,
    Record,
    history_totals,
    shares_period,
    solve,
)

GRID = "grid"
TARIFF = 0.34
FEED_IN = 0.08
PRICES = {"pv": 0.10, "roof": 0.10, "carport": 0.10, "bat": 0.15}


def _home(**kwargs) -> HomeInputs:
    return HomeInputs(GRID, **{"fed_in": 4000.0, "tariff": TARIFF, **kwargs})


def _pv(uid: str = "pv", **kwargs) -> DeviceInputs:
    return DeviceInputs(
        uid, PV_SYSTEM, **{"exports": True, "feed_in_tariff": FEED_IN, **kwargs}
    )


def _battery(uid: str = "bat", **kwargs) -> DeviceInputs:
    return DeviceInputs(
        uid,
        BATTERY,
        **{"charged": 2500.0, "grid_charged": 0.0, "discharged": 2200.0, **kwargs},
    )


def _solve(home: HomeInputs, *devices: DeviceInputs) -> dict[str, Record]:
    solution = solve(home, devices)
    assert solution.problems == []
    return solution.records


def _totals(record: Record, prices: dict | None = None) -> dict:
    return history_totals(record, (prices or PRICES).get).values


def _problems(home: HomeInputs, *devices: DeviceInputs) -> list[Problem]:
    solution = solve(home, devices)
    assert solution.records == {}
    return solution.problems


# ---------------------------------------------------------------------------
# One PV system, one battery charging only from it
# ---------------------------------------------------------------------------


def _single() -> dict[str, Record]:
    return _solve(_home(), _pv(produced=10000.0), _battery(charge_from=("pv",)))


def test_the_battery_share_is_taken_out_of_the_pv() -> None:
    """Of 10,000 kWh produced, 4,000 were fed in and 2,500 charged the
    battery, so 3,500 reached the home directly. The battery delivered its
    2,200 into the home and charged entirely from the PV system.
    """
    records = _single()
    pv, bat = records["pv"].flows, records["bat"].flows

    assert (pv.to_home, pv.exported) == pytest.approx((3500.0, 4000.0))
    assert (bat.to_home, bat.exported, bat.from_grid) == pytest.approx((2200.0, 0.0, 0.0))
    assert bat.from_pv == pytest.approx({"pv": 2500.0})


def test_single_pv_and_battery_carry_the_worked_example() -> None:
    """Every carried-over total of the plan's first example.

    The battery pays the PV 2,500 × 0.08 = 200 for the energy it stored.

    PV: 3,500 × 0.34 + 200 = 1,390 saved, of which 1,190 avoided; 790
    levelized (− 6,000 × 0.10, its LCOE on everything that reached the home
    or the battery); 320 export compensation (4,000 × 0.08); 1,710 financial
    return; 710 levelized (790 + 320 − 4,000 × 0.10). Entering
    self-consumption (6,000 kWh) would have read 2,040, the battery's
    2,500 kWh counted twice.

    Battery: 2,200 × 0.34 − 200 = 548 saved, of which 748 avoided; 218
    levelized (− 2,200 × 0.15 for its own LCOS); no grid charging, so no
    standard operating cost, and 250 levelized (2,500 × 0.10, the cost of
    making what it stored).
    """
    records = _single()

    assert _totals(records["pv"]) == pytest.approx({
        "total_cost_savings": 1390.0,
        "total_avoided_cost": 1190.0,
        "total_levelized_cost_savings": 790.0,
        "total_export_compensation": 320.0,
        "total_financial_return": 1710.0,
        "total_levelized_financial_return": 710.0,
    })
    assert _totals(records["bat"]) == pytest.approx({
        "total_cost_savings": 548.0,
        "total_avoided_cost": 748.0,
        "total_levelized_cost_savings": 218.0,
        "total_export_compensation": 0.0,
        "total_financial_return": 548.0,
        "total_levelized_financial_return": 218.0,
        "total_operating_cost": 0.0,
        "total_levelized_operating_cost": 250.0,
    })


def test_a_correction_restates_both_devices_history() -> None:
    """Lifetime costs are priced at read time, so a correction restates the
    history. Doubling both (LCOE 0.10 → 0.20, LCOS 0.15 → 0.30): the PV
    saves 1,390 − 6,000 × 0.20 = 190 levelized, the battery
    548 − 2,200 × 0.30 = −112. Standard savings do not move.

    The PV's LCOE alone restates only the PV: the battery pays the PV's
    feed-in rate for what it stored, whatever making it cost, so it keeps
    its 218.
    """
    records = _single()
    prices = {**PRICES, "pv": 0.20, "bat": 0.30}

    pv, bat = _totals(records["pv"], prices), _totals(records["bat"], prices)
    assert pv["total_levelized_cost_savings"] == pytest.approx(190.0)
    assert bat["total_levelized_cost_savings"] == pytest.approx(-112.0)
    assert pv["total_cost_savings"] == pytest.approx(1390.0)
    assert bat["total_cost_savings"] == pytest.approx(548.0)

    prices = {**PRICES, "pv": 0.20}
    assert _totals(records["pv"], prices)["total_levelized_cost_savings"] == (
        pytest.approx(190.0)
    )
    assert _totals(records["bat"], prices)["total_levelized_cost_savings"] == (
        pytest.approx(218.0)
    )


def test_grid_import_is_not_a_source() -> None:
    """A battery allowed the grid still charges from the PV system unless
    grid charging is entered. Live, "the grid goes first"; on a year's totals
    that would hand the battery all of its charging from the grid, because
    the home imports far more than the battery ever charges.
    """
    records = _solve(
        _home(), _pv(produced=10000.0), _battery(charge_from=(GRID, "pv"))
    )
    assert records["bat"].flows.from_grid == 0.0
    assert records["bat"].flows.from_pv == pytest.approx({"pv": 2500.0})


def test_grid_charging_is_the_entered_figure() -> None:
    """500 of the 2,500 kWh charged came from the grid: they cost the battery
    500 × 0.34 = 170, which comes off its savings and is its operating cost.
    Only the other 2,000 come out of the PV's output, so 4,000 reach the
    home from the PV, and the battery pays it 2,000 × 0.08 = 160 for them:
    748 − 170 − 160 = 418.
    """
    records = _solve(
        _home(), _pv(produced=10000.0), _battery(grid_charged=500.0)
    )
    assert records["bat"].flows.from_pv == pytest.approx({"pv": 2000.0})
    assert records["pv"].flows.to_home == pytest.approx(4000.0)

    bat = _totals(records["bat"])
    assert bat["total_cost_savings"] == pytest.approx(418.0)
    assert bat["total_operating_cost"] == pytest.approx(170.0)


def test_avoided_cost_is_the_savings_before_the_operating_cost() -> None:
    """The battery's 2,200 kWh into the home avoided 2,200 × 0.34 = 748,
    whatever it charged from. Its savings (418) are that less the 170 its
    grid charging cost and the 160 it paid the PV for its stored energy. The
    PV's avoided cost is the 4,000 kWh it put into the home × 0.34 = 1,360;
    its savings (1,520) add the 160 it was paid. As for the counted part,
    the transfer is a saving, never an avoided cost, and it cancels out.
    """
    records = _solve(
        _home(), _pv(produced=10000.0), _battery(grid_charged=500.0)
    )
    pv, bat = _totals(records["pv"]), _totals(records["bat"])
    assert bat["total_avoided_cost"] == pytest.approx(748.0)
    assert bat["total_avoided_cost"] - bat["total_operating_cost"] - 160.0 == (
        pytest.approx(bat["total_cost_savings"])
    )
    assert pv["total_avoided_cost"] == pytest.approx(1360.0)
    assert pv["total_cost_savings"] == pytest.approx(1520.0)


def test_an_amounts_only_battery_carries_no_avoided_cost() -> None:
    """A battery's entered savings are net of its grid charging, which an
    amounts-only history does not know, so its avoided cost carries nothing
    and says why. A PV system's entered savings are its avoided cost: it
    has no charging to take off.
    """
    home = HomeInputs(GRID)
    pv = _pv(savings=1500.0)
    bat = DeviceInputs("bat", BATTERY, savings=600.0)

    records = _solve(home, pv, bat)
    assert _totals(records["pv"])["total_avoided_cost"] == pytest.approx(1500.0)
    totals = history_totals(records["bat"], PRICES.get)
    assert totals.values["total_avoided_cost"] is None
    assert totals.missing["total_avoided_cost"] == MISSING_ENERGY


def test_batteries_do_not_charge_each_other() -> None:
    """An unrestricted battery may charge from any PV system, never from the
    other battery's discharge: over a period both appear as sources and
    sinks, and battery-to-battery transfer would only absorb PV energy.
    """
    records = _solve(
        _home(),
        _pv(produced=10000.0),
        _battery("bat", charged=1000.0, discharged=900.0),
        _battery("bat2", charged=1000.0, discharged=900.0),
    )
    assert records["bat"].flows.from_pv == pytest.approx({"pv": 1000.0})
    assert records["bat2"].flows.from_pv == pytest.approx({"pv": 1000.0})
    assert records["pv"].flows.to_home == pytest.approx(10000.0 - 4000.0 - 2000.0)


# ---------------------------------------------------------------------------
# Stored energy: the battery pays the PV its feed-in rate
# ---------------------------------------------------------------------------


def test_stored_pv_is_paid_at_its_feed_in_rate() -> None:
    """The decision. Without the battery, the 2,500 kWh it stored would have
    been fed in at 0.08 (a period's totals cannot tell the moments the home
    was importing instead), so the battery pays the PV 200 and the PV earns
    it. That moves 200 of savings, and with it the PV's LCOE on the
    2,500 kWh (250) from the battery to the PV. Combined, nothing moves:
    1,938 standard and 1,008 levelized, as under the rule before.
    """
    records = _single()
    assert records["bat"].flows.stored_price == {"pv": FEED_IN}
    assert records["pv"].flows.to_batteries == pytest.approx({"bat": 2500.0})

    pv, bat = _totals(records["pv"]), _totals(records["bat"])
    assert pv["total_cost_savings"] - 1190.0 == pytest.approx(200.0)
    assert 748.0 - bat["total_cost_savings"] == pytest.approx(200.0)
    assert pv["total_cost_savings"] + bat["total_cost_savings"] == pytest.approx(1938.0)
    assert pv["total_levelized_cost_savings"] + bat[
        "total_levelized_cost_savings"
    ] == pytest.approx(840.0 + 168.0)


def test_a_pv_that_may_not_export_is_paid_nothing() -> None:
    """A PV system that may not export would have curtailed what the battery
    stored, so the battery pays nothing for it: its savings stay 748. The PV
    still carries its LCOE on everything it made, so its levelized savings
    are 7,500 × 0.34 − 10,000 × 0.10 = 1,550, the battery's
    748 − 2,200 × 0.15 = 418.
    """
    records = _solve(
        _home(fed_in=0.0), _pv(produced=10000.0, exports=False), _battery()
    )
    assert records["bat"].flows.stored_price == {"pv": 0.0}

    pv, bat = _totals(records["pv"]), _totals(records["bat"])
    assert pv["total_cost_savings"] == pytest.approx(2550.0)
    assert bat["total_cost_savings"] == pytest.approx(748.0)
    assert pv["total_levelized_cost_savings"] == pytest.approx(1550.0)
    assert bat["total_levelized_cost_savings"] == pytest.approx(418.0)


def test_an_entered_savings_amount_keeps_the_old_rule() -> None:
    """The battery entered its app's savings (800): that amount is taken as
    it is, so neither device books the transfer. The PV earns nothing for
    the stored energy (1,190), and the battery's levelized savings still
    take the PV's LCOE on what it stored: 800 − 330 − 250 = 220.
    """
    records = _solve(_home(), _pv(produced=10000.0), _battery(savings=800.0))
    assert records["bat"].flows.stored_price == {}
    assert records["pv"].flows.to_batteries == {}

    pv, bat = _totals(records["pv"]), _totals(records["bat"])
    assert pv["total_cost_savings"] == pytest.approx(1190.0)
    assert pv["total_levelized_cost_savings"] == pytest.approx(840.0)
    assert bat["total_cost_savings"] == pytest.approx(800.0)
    assert bat["total_levelized_cost_savings"] == pytest.approx(220.0)


def test_a_standalone_battery_keeps_the_old_rule() -> None:
    """A battery added later has a period of its own; the PV systems' side
    of that period is not in their history, so the transfer could be booked
    on one side only. It is booked on neither: the battery's 1,000 kWh from
    each PV system cost it their LCOE in levelized savings, nothing in
    standard ones (1,800 × 0.30 = 540).
    """
    records = _solve(
        _home(),
        _pv("roof", produced=8000.0),
        _pv("carport", produced=2000.0),
        _battery("late", standalone=True, charged=2000.0, discharged=1800.0, tariff=0.30),
    )
    assert records["late"].flows.stored_price == {}
    late = _totals(records["late"], {**PRICES, "late": 0.15})
    assert late["total_cost_savings"] == pytest.approx(540.0)
    assert late["total_levelized_cost_savings"] == pytest.approx(
        540.0 - 1800 * 0.15 - 2000 * 0.10
    )


def test_an_unknown_feed_in_rate_blanks_both_sides() -> None:
    """The PV may export but has no feed-in rate, so what the battery pays
    for its stored energy is unknown: both devices' savings carry nothing
    and say why, never one without the other.
    """
    records = _solve(_home(), _pv(produced=10000.0, feed_in_tariff=None), _battery())
    pv = history_totals(records["pv"], PRICES.get)
    bat = history_totals(records["bat"], PRICES.get)
    assert pv.missing["total_cost_savings"] == MISSING_FEED_IN_TARIFF
    assert bat.missing["total_cost_savings"] == MISSING_FEED_IN_TARIFF
    assert bat.values["total_operating_cost"] == 0.0


def test_a_record_stored_before_the_transfer_reads_as_before() -> None:
    """A record stored without the transfer's fields prices as it did: the
    battery pays nothing and takes the PV's LCOE. The store re-solves such
    records once at setup (``test_history_store.py``), so this only guards
    reading one.
    """
    data = _single()["bat"].to_dict()
    del data["flows"]["stored_price"], data["flows"]["to_batteries"]
    bat = _totals(Record.from_dict(data))
    assert bat["total_cost_savings"] == pytest.approx(748.0)
    assert bat["total_levelized_cost_savings"] == pytest.approx(168.0)


# ---------------------------------------------------------------------------
# Two PV systems
# ---------------------------------------------------------------------------


def test_interchangeable_pv_systems_split_in_proportion_to_output() -> None:
    """Roof (8,000 kWh) and carport (2,000 kWh) are allowed by the same
    sinks, so they split 8 : 2: exports 3,200 / 800, battery charging
    2,000 / 500, home 2,800 / 700. Combined savings are 1,938 whatever the
    split; it only decides which device earned what.
    """
    records = _solve(
        _home(),
        _pv("roof", produced=8000.0),
        _pv("carport", produced=2000.0),
        _battery(),
    )
    roof, carport = records["roof"].flows, records["carport"].flows
    assert (roof.exported, carport.exported) == pytest.approx((3200.0, 800.0))
    assert (roof.to_home, carport.to_home) == pytest.approx((2800.0, 700.0))
    assert records["bat"].flows.from_pv == pytest.approx(
        {"roof": 2000.0, "carport": 500.0}
    )

    combined = sum(_totals(r)["total_cost_savings"] for r in records.values())
    assert combined == pytest.approx(1938.0)


def test_own_feed_in_is_used_as_entered() -> None:
    """The roof's own feed-in of 3,500 kWh (from the grid operator's
    statement) is taken as it is, so the carport fed in the remaining 500.
    The battery then splits over what is left, roof 4,500 : carport 1,500,
    taking 1,875 and 625, and the home gets 2,625 and 875.
    """
    records = _solve(
        _home(),
        _pv("roof", produced=8000.0, fed_in=3500.0),
        _pv("carport", produced=2000.0),
        _battery(),
    )
    roof, carport = records["roof"].flows, records["carport"].flows
    assert (roof.exported, carport.exported) == pytest.approx((3500.0, 500.0))
    assert records["bat"].flows.from_pv == pytest.approx(
        {"roof": 1875.0, "carport": 625.0}
    )
    assert (roof.to_home, carport.to_home) == pytest.approx((2625.0, 875.0))


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------


def test_an_entered_amount_wins_and_levelized_still_follows_the_kwh() -> None:
    """With kWh and an entered savings figure of 1,300, the standard savings
    read exactly 1,300, and the levelized ones subtract the energy's current
    cost: 1,300 − 3,500 × 0.10 = 950. A correction still restates that part.
    """
    records = _solve(_home(), _pv(produced=10000.0, savings=1300.0), _battery())
    pv = _totals(records["pv"])
    assert pv["total_cost_savings"] == pytest.approx(1300.0)
    assert pv["total_levelized_cost_savings"] == pytest.approx(950.0)
    assert _totals(records["pv"], {**PRICES, "pv": 0.20})[
        "total_levelized_cost_savings"
    ] == pytest.approx(600.0)


def test_amounts_only_is_taken_at_face_value() -> None:
    """Without kWh, the entered amounts are the history: savings 1,500,
    export compensation 300, financial return 1,800. The levelized savings
    are only known if entered too; the levelized financial return also needs
    the exported kWh it would subtract the LCOE of, so it carries nothing,
    and says why.
    """
    home = HomeInputs(GRID)
    pv = _pv(savings=1500.0, export_compensation=300.0)

    totals = history_totals(_solve(home, pv)["pv"], PRICES.get)
    assert totals.values["total_cost_savings"] == pytest.approx(1500.0)
    assert totals.values["total_financial_return"] == pytest.approx(1800.0)
    assert totals.values["total_levelized_cost_savings"] is None
    assert totals.missing["total_levelized_cost_savings"] == MISSING_ENERGY

    pv = _pv(savings=1500.0, export_compensation=300.0, levelized_savings=1000.0)
    totals = history_totals(_solve(home, pv)["pv"], PRICES.get)
    assert totals.values["total_levelized_cost_savings"] == pytest.approx(1000.0)
    assert totals.values["total_levelized_financial_return"] is None
    assert totals.missing["total_levelized_financial_return"] == MISSING_ENERGY


def test_a_home_amount_is_split_by_the_calculated_savings() -> None:
    """Total savings of 2,000 entered for the home are split in proportion
    to the calculated 1,390 and 548 (the stored-energy transfer of 200
    included): PV 1,434.47, battery 565.53. The levelized figures still
    follow the kWh: 1,434.47 − 6,000 × 0.10 = 834.47 and
    565.53 − 2,200 × 0.15 = 235.53.
    """
    records = _solve(_home(savings=2000.0), _pv(produced=10000.0), _battery())
    pv, bat = _totals(records["pv"]), _totals(records["bat"])
    assert pv["total_cost_savings"] == pytest.approx(2000.0 * 1390 / 1938, abs=0.01)
    assert bat["total_cost_savings"] == pytest.approx(2000.0 * 548 / 1938, abs=0.01)
    assert pv["total_levelized_cost_savings"] == pytest.approx(834.47, abs=0.01)
    assert bat["total_levelized_cost_savings"] == pytest.approx(235.53, abs=0.01)
    # A dealt-out amount is the truth for avoided cost too, the transfer
    # taken back out.
    assert pv["total_avoided_cost"] == pytest.approx(pv["total_cost_savings"] - 200.0)
    assert bat["total_avoided_cost"] == pytest.approx(bat["total_cost_savings"] + 200.0)


def test_a_home_amount_skips_what_devices_entered_themselves() -> None:
    """The battery entered 800 itself, so the PV system gets the other 1,200
    of a home total of 2,000, the only device left to give it to.
    """
    records = _solve(
        _home(savings=2000.0), _pv(produced=10000.0), _battery(savings=800.0)
    )
    assert records["pv"].savings == pytest.approx(1200.0)
    assert records["bat"].savings == pytest.approx(800.0)


def test_home_export_compensation_is_split_by_exported_kwh() -> None:
    """A home export compensation of 400 is split 3,200 : 800 kWh between
    roof and carport: 320 and 80. The battery does not export and gets none.
    """
    records = _solve(
        _home(export_compensation=400.0),
        _pv("roof", produced=8000.0),
        _pv("carport", produced=2000.0),
        _battery(),
    )
    assert records["roof"].export_compensation == pytest.approx(320.0)
    assert records["carport"].export_compensation == pytest.approx(80.0)
    assert records["bat"].export_compensation is None


def test_a_home_amount_without_kwh_goes_to_a_single_device() -> None:
    """With only one PV system there is nothing to split by, and nothing to
    split: it gets the whole amount.
    """
    records = _solve(HomeInputs(GRID, savings=900.0), _pv())
    assert records["pv"].savings == pytest.approx(900.0)


# ---------------------------------------------------------------------------
# The average grid tariff
# ---------------------------------------------------------------------------


def test_a_devices_own_tariff_carries_its_savings() -> None:
    """The grid has no average tariff, but the PV system was given its own
    (0.30): its 6,000 kWh into the home save 1,800. Without either, the
    savings carry nothing while the export compensation still does.
    """
    records = _solve(_home(tariff=None, fed_in=0.0), _pv(produced=6000.0, tariff=0.30))
    assert _totals(records["pv"])["total_cost_savings"] == pytest.approx(1800.0)

    records = _solve(_home(tariff=None), _pv(produced=10000.0))
    totals = history_totals(records["pv"], PRICES.get)
    assert totals.missing["total_cost_savings"] == MISSING_TARIFF
    assert totals.values["total_export_compensation"] == pytest.approx(320.0)


def test_a_devices_own_tariff_wins_and_the_grids_is_the_fallback() -> None:
    """The grid's 0.34 is the home's average; the battery was given its own
    0.30 and uses it, the PV system was not and falls back to the grid's.
    The 200 the battery pays for its stored energy needs no tariff.
    """
    records = _solve(_home(), _pv(produced=10000.0), _battery(tariff=0.30))
    assert records["pv"].tariff == 0.34
    assert records["bat"].tariff == 0.30
    assert _totals(records["bat"])["total_cost_savings"] == pytest.approx(
        2200 * 0.30 - 200
    )


# ---------------------------------------------------------------------------
# The inclusion rule
# ---------------------------------------------------------------------------


def test_a_total_missing_a_term_carries_nothing() -> None:
    """Without an average tariff the savings cannot be calculated, so they
    carry no history, but the export compensation, which needs only the
    feed-in tariff, still does. Without the battery's LCOS its levelized
    savings carry nothing either. Each says why.
    """
    records = _solve(_home(tariff=None), _pv(produced=10000.0), _battery())

    pv = history_totals(records["pv"], PRICES.get)
    assert pv.values["total_cost_savings"] is None
    assert pv.missing["total_cost_savings"] == MISSING_TARIFF
    assert pv.values["total_export_compensation"] == pytest.approx(320.0)

    records = _solve(_home(), _pv(produced=10000.0), _battery())
    bat = history_totals(records["bat"], {"pv": 0.10}.get)
    assert bat.values["total_levelized_cost_savings"] is None
    assert bat.missing["total_levelized_cost_savings"] == MISSING_PRICE
    assert bat.values["total_cost_savings"] == pytest.approx(548.0)


def test_energy_that_is_not_there_needs_no_price() -> None:
    """A battery that never charged from the grid has no grid charging to
    price, so its operating cost is a known 0, tariff or not.
    """
    records = _solve(_home(tariff=None), _pv(produced=10000.0), _battery())
    assert _totals(records["bat"])["total_operating_cost"] == 0.0


# ---------------------------------------------------------------------------
# Waiting for another device
# ---------------------------------------------------------------------------


def test_a_missing_exporting_device_blocks_the_split() -> None:
    """The carport exports but has no history yet, so part of the home's
    feed-in is its own and the roof's share cannot be told. Nothing is split:
    the roof's totals wait for the carport and say so. Entering 0 kWh for the
    carport states that it has none and releases the split.
    """
    records = _solve(_home(), _pv("roof", produced=8000.0), _pv("carport"))
    assert records["roof"].flows is None
    assert records["roof"].waiting_for == ("carport",)
    totals = history_totals(records["roof"], PRICES.get)
    assert totals.missing["total_cost_savings"] == MISSING_WAITING

    records = _solve(
        _home(), _pv("roof", produced=8000.0), _pv("carport", produced=0.0)
    )
    assert records["roof"].flows.exported == pytest.approx(4000.0)


def test_the_split_waits_for_the_homes_feed_in() -> None:
    """Without the grid's fed-in figure an exporting PV system without its
    own feed-in cannot know how much it exported, so it waits for the grid.
    """
    records = _solve(_home(fed_in=None), _pv(produced=10000.0))
    assert records["pv"].waiting_for == (GRID,)


def test_a_missing_pv_system_a_battery_charged_from_blocks_the_split() -> None:
    """The battery charged 2,500 kWh locally and may charge from the carport,
    which has no history: how much of the charging was the roof's is unknown.
    """
    records = _solve(
        _home(fed_in=0.0),
        _pv("roof", produced=8000.0, exports=False),
        _pv("carport", exports=False),
        _battery(),
    )
    assert records["bat"].waiting_for == ("carport",)
    assert records["roof"].waiting_for == ("carport",)


# ---------------------------------------------------------------------------
# Standalone devices
# ---------------------------------------------------------------------------


def test_a_standalone_pv_system_uses_its_own_figures() -> None:
    """Added later, the PV system stands alone: 3,000 produced, 1,000 fed in
    and 500 into batteries leave 1,500 for the home, priced at its own
    average tariff of 0.30: 450 saved.
    """
    records = _solve(
        _home(),
        _pv(
            "late", standalone=True, produced=3000.0, fed_in=1000.0,
            into_batteries=500.0, tariff=0.30,
        ),
    )
    assert records["late"].flows.to_home == pytest.approx(1500.0)
    assert _totals(records["late"])["total_cost_savings"] == pytest.approx(450.0)


def test_a_standalone_battery_splits_its_charging_evenly() -> None:
    """With no shared totals to weigh by, a battery added later splits its
    local charging evenly over the PV systems it may charge from: 1,000 each.
    """
    records = _solve(
        _home(),
        _pv("roof", produced=8000.0),
        _pv("carport", produced=2000.0),
        _battery("late", standalone=True, charged=2000.0, discharged=1800.0, tariff=0.30),
    )
    assert records["late"].flows.from_pv == pytest.approx(
        {"roof": 1000.0, "carport": 1000.0}
    )
    assert records["late"].tariff == 0.30


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("devices", "home", "expected"),
    [
        pytest.param(
            [_battery(discharged=None)], _home(),
            Problem(ERROR_PARTIAL_ENERGY, "bat", "discharged"),
            id="battery-charged-without-discharged",
        ),
        pytest.param(
            [_pv(fed_in=100.0)], _home(),
            Problem(ERROR_PARTIAL_ENERGY, "pv", "produced"),
            id="pv-fed-in-without-produced",
        ),
        pytest.param(
            [_pv(produced=10000.0), _battery(grid_charged=3000.0)], _home(),
            Problem(ERROR_GRID_CHARGED_EXCEEDS_CHARGED, "bat", "grid_charged"),
            id="grid-charged-above-charged",
        ),
        pytest.param(
            [_pv(produced=1000.0, fed_in=2000.0)], _home(),
            Problem(ERROR_FED_IN_EXCEEDS_OUTPUT, "pv", "fed_in"),
            id="own-feed-in-above-production",
        ),
        pytest.param(
            [_pv(produced=10000.0, fed_in=5000.0)], _home(),
            Problem(ERROR_FED_IN_EXCEEDS_HOME, GRID, "fed_in"),
            id="own-feed-ins-above-the-home",
        ),
        pytest.param(
            [_pv(produced=10000.0), _battery(charged=0.0, discharged=2200.0)],
            _home(fed_in=10500.0),
            Problem(ERROR_FED_IN_EXCEEDS_PRODUCTION, GRID, "fed_in"),
            id="home-feed-in-above-what-exporters-produced",
        ),
        pytest.param(
            [_pv(produced=1000.0), _battery(discharged=0.0)], _home(fed_in=500.0),
            Problem(ERROR_DOES_NOT_BALANCE),
            id="more-out-than-in",
        ),
        pytest.param(
            [_pv(produced=10000.0), _battery(charge_from=(GRID,))], _home(),
            Problem(ERROR_CHARGING_NOT_COVERED, "bat", "charged"),
            id="local-charging-without-a-permitted-pv",
        ),
        pytest.param(
            [_pv("late", standalone=True, produced=1000.0, tariff=0.3)], _home(),
            Problem(ERROR_FED_IN_REQUIRED, "late", "fed_in"),
            id="standalone-exporter-without-own-feed-in",
        ),
        pytest.param(
            [_pv("late", standalone=True, produced=1000.0, fed_in=100.0)], _home(),
            Problem(ERROR_TARIFF_REQUIRED, "late", "tariff"),
            id="standalone-without-tariff",
        ),
        pytest.param(
            [_pv(produced=10000.0), _battery(charged=2500.0, grid_charged=2500.0)],
            _home(savings=2000.0),
            Problem(ERROR_SAVINGS_NOT_SPLITTABLE, GRID, "savings"),
            id="home-savings-with-a-grid-charging-battery",
        ),
        pytest.param(
            [_pv("roof"), _pv("carport")], HomeInputs(GRID, savings=900.0),
            Problem(ERROR_SAVINGS_NOT_SPLITTABLE, GRID, "savings"),
            id="home-savings-without-kwh-for-two-devices",
        ),
        pytest.param(
            [_pv("roof"), _pv("carport")],
            HomeInputs(GRID, export_compensation=400.0),
            Problem(ERROR_EXPORT_COMPENSATION_NOT_SPLITTABLE, GRID, "export_compensation"),
            id="home-export-compensation-without-kwh-for-two-devices",
        ),
    ],
)
def test_figures_that_cannot_balance_are_refused(devices, home, expected) -> None:
    """Each set of figures is impossible or cannot be attributed, so the save
    is refused, pointing at the figure that is off. Nothing is stored.
    """
    assert expected in _problems(home, *devices)


# ---------------------------------------------------------------------------
# Storage and periods
# ---------------------------------------------------------------------------


def test_a_record_round_trips_through_storage() -> None:
    """Records are stored as plain dicts in the config entry; reading one
    back gives the same record, so the history prices the same after a
    restart.
    """
    for record in _single().values():
        assert Record.from_dict(record.to_dict()) == record


def test_devices_set_up_together_share_a_period() -> None:
    """Within 24 hours of the grid a device shares its period; a device
    added two days later is standalone.
    """
    grid = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    assert shares_period(grid, grid + timedelta(hours=3))
    assert not shares_period(grid, grid + timedelta(days=2))


# ---------------------------------------------------------------------------
# Tolerance: app figures are rounded and come from different meters
# ---------------------------------------------------------------------------


def test_rounded_figures_are_accepted() -> None:
    """The roof's statement says 3,500.4 kWh fed in, the carport's 500, the
    grid meter 4,000 for the whole home: 0.4 kWh apart, as rounded figures
    from different meters always are. That is accepted; the roof keeps its
    own figure and the home's feed-in has nothing left to split.
    """
    records = _solve(
        _home(),
        _pv("roof", produced=8000.0, fed_in=3500.4),
        _pv("carport", produced=2000.0, fed_in=500.0),
    )
    assert records["roof"].flows.exported == pytest.approx(3500.4)
    assert records["carport"].flows.exported == pytest.approx(500.0)


def test_a_real_mismatch_is_still_refused() -> None:
    """Own feed-ins of 4,100 kWh against a home total of 4,000 are 2.5 %
    apart, beyond what rounding or meters explain (1 %, at least 1 kWh), so
    they are refused.
    """
    problems = _problems(
        _home(),
        _pv("roof", produced=8000.0, fed_in=3600.0),
        _pv("carport", produced=2000.0, fed_in=500.0),
    )
    assert Problem(ERROR_FED_IN_EXCEEDS_HOME, GRID, "fed_in") in problems


def test_a_tolerated_shortfall_never_breaks_a_restriction() -> None:
    """The grid meter reads 20 kWh more than the PV system's own feed-in,
    and the only other device that may feed in discharged 5 kWh. That is
    within the tolerance, but the battery that may not feed in still never
    exports: the 15 kWh left over simply stay unattributed.
    """
    records = _solve(
        _home(fed_in=3467.0),
        _pv(produced=5134.0, fed_in=3447.0),
        _battery("bat", exports=True, charged=5.0, discharged=5.0),
        _battery("captive", charged=70.0, discharged=63.0),
    )
    assert records["captive"].flows.exported == 0.0
    assert records["bat"].flows.exported == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Randomized: the books always balance
# ---------------------------------------------------------------------------


def _slack(*figures: float) -> float:
    """The tolerance ``history.py`` allows, restated: 1 % or 1 kWh."""
    return max(1.0, 0.01 * max(abs(f) for f in figures))


def _real_home(rng) -> tuple[HomeInputs, list[DeviceInputs]]:
    """Figures read off a real flow that respects every restriction,
    rounded to whole kWh, with the grid meter up to 0.5 % off the devices'.
    """
    pvs = [f"pv{i}" for i in range(rng.randint(1, 3))]
    bats = [f"bat{i}" for i in range(rng.randint(0, 2))]
    exports = {uid: rng.random() < 0.8 for uid in pvs + bats}
    produced = {p: 0.0 for p in pvs}
    fed_in = {}
    for p in pvs:
        fed_in[p] = rng.uniform(0, 4000) if exports[p] else 0.0
        produced[p] += rng.uniform(0, 5000) + fed_in[p]
    devices, batteries = [], []
    for b in bats:
        charge_from = (
            tuple(rng.sample(pvs, rng.randint(1, len(pvs)))) if rng.random() < 0.5 else ()
        )
        local = 0.0
        for p in charge_from or pvs:
            kwh = rng.uniform(0, 1500)
            produced[p] += kwh
            local += kwh
        grid = rng.uniform(0, 500) if rng.random() < 0.3 else 0.0
        discharged = (local + grid) * rng.uniform(0.7, 0.95)
        fed_in[b] = discharged * rng.uniform(0, 0.3) if exports[b] else 0.0
        batteries.append(DeviceInputs(
            b, BATTERY, exports=exports[b], feed_in_tariff=FEED_IN,
            charge_from=charge_from, charged=round(local + grid),
            grid_charged=round(grid), discharged=round(discharged),
            fed_in=round(fed_in[b]) if rng.random() < 0.3 else None,
        ))
    for p in pvs:
        devices.append(DeviceInputs(
            p, PV_SYSTEM, exports=exports[p], feed_in_tariff=FEED_IN,
            produced=round(produced[p]),
            fed_in=round(fed_in[p]) if rng.random() < 0.3 else None,
        ))
    home_fed_in = round(sum(fed_in.values()) * rng.uniform(0.995, 1.005))
    return _home(fed_in=home_fed_in), devices + batteries


def _assert_balanced(home: HomeInputs, devices: list[DeviceInputs], records) -> None:
    """Every device's energy balances within the tolerance, every
    restriction holds, and the money adds up.
    """
    by_uid = {d.uid: d for d in devices}
    into_batteries = {d.uid: 0.0 for d in devices if d.kind == PV_SYSTEM}
    for uid, record in records.items():
        device, flows = by_uid[uid], record.flows
        assert flows.to_home >= -1e-6 and flows.exported >= -1e-6
        if not device.exports and device.fed_in is None:
            assert flows.exported == 0.0, "a device that may not feed in exported"
        if device.kind == BATTERY:
            assert abs(flows.to_home + flows.exported - device.discharged) <= _slack(device.discharged)
            assert abs(sum(flows.from_pv.values()) + flows.from_grid - device.charged) <= (
                _slack(device.charged)
            )
            for pv, kwh in flows.from_pv.items():
                assert pv in into_batteries, "a battery charged from a battery"
                assert not device.charge_from or pv in device.charge_from or kwh == 0.0
                into_batteries[pv] += kwh
    for uid, charged in into_batteries.items():
        device, flows = by_uid[uid], records[uid].flows
        assert abs(flows.to_home + flows.exported + charged - device.produced) <= (
            _slack(device.produced)
        )
    for record in records.values():
        totals = history_totals(record, PRICES.get).values
        assert totals["total_financial_return"] == pytest.approx(
            totals["total_cost_savings"] + totals["total_export_compensation"]
        )


@pytest.mark.parametrize("seed", range(5))
def test_figures_from_a_real_flow_are_always_accepted(seed: int) -> None:
    """Figures that describe what really happened, rounded and off by a
    little between meters as real app figures are, are never refused, and
    what they solve to balances. 200 random homes per seed.
    """
    import random

    rng = random.Random(seed)
    for _ in range(200):
        home, devices = _real_home(rng)
        solution = solve(home, devices)
        assert solution.problems == [], (home, devices)
        assert not any(r.waiting_for for r in solution.records.values())
        _assert_balanced(home, devices, solution.records)


@pytest.mark.parametrize("seed", range(5))
def test_whatever_is_accepted_balances(seed: int) -> None:
    """Arbitrary figures are often impossible and refused; whatever is
    accepted balances within the tolerance and keeps every restriction.
    200 random homes per seed.
    """
    import random

    rng = random.Random(100 + seed)
    for _ in range(200):
        pvs = [f"pv{i}" for i in range(rng.randint(1, 3))]
        devices = [
            DeviceInputs(
                p, PV_SYSTEM, exports=rng.random() < 0.8, feed_in_tariff=FEED_IN,
                produced=round(rng.uniform(0, 10000)),
                fed_in=round(rng.uniform(0, 4000)) if rng.random() < 0.3 else None,
            )
            for p in pvs
        ]
        for i in range(rng.randint(0, 2)):
            charged = round(rng.uniform(0, 3000))
            devices.append(DeviceInputs(
                f"bat{i}", BATTERY, exports=rng.random() < 0.2, feed_in_tariff=FEED_IN,
                charge_from=(
                    tuple(rng.sample(pvs, rng.randint(1, len(pvs))))
                    if rng.random() < 0.5 else ()
                ),
                charged=charged,
                grid_charged=round(rng.uniform(0, charged)) if rng.random() < 0.3 else None,
                discharged=round(charged * rng.uniform(0.7, 1.0)),
            ))
        home = _home(fed_in=round(rng.uniform(0, 12000)))
        solution = solve(home, devices)
        if not solution.problems:
            _assert_balanced(home, devices, solution.records)
