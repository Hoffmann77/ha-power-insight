"""Tests for the "Already accumulated" section of the device forms.

The section takes the history carried over from a device's app, stores it
as entered on the subentry, and refuses figures that cannot balance, checked
together with every other device's.
"""

from __future__ import annotations

import copy
import json
import pathlib
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight import history
from custom_components.power_insight.config_flow import (
    HISTORY_AMOUNTS,
    HISTORY_ENERGY,
    HISTORY_SECTIONS,
)

from .conftest import (
    BASE_OPTIONS,
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_grid_subentry_data,
    make_pv_subentry_data,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

TRANSLATION_FILES = (
    "custom_components/power_insight/strings.json",
    "custom_components/power_insight/translations/en.json",
)
PV_INPUT = {
    "name": "Rooftop Solar",
    "power_entity": "sensor.solar_power",
    "power_entity_inverted": False,
    "exports_power": True,
    "export_compensation": 0.08,
}


def _entry(*, grid_since: str | None = None, grid_history: dict | None = None,
           pv_history: dict | None = None) -> MockConfigEntry:
    """A grid counted from ``grid_since`` (now by default) and, with
    ``pv_history``, a PV system with that history.
    """
    since = grid_since or dt_util.utcnow().isoformat()
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["counting_since"] = since
    if grid_history is not None:
        grid["data"]["history"] = grid_history
    subentries = [grid]
    if pv_history is not None:
        pv = copy.deepcopy(make_pv_subentry_data())
        pv["data"]["counting_since"] = since
        pv["data"]["history"] = pv_history
        subentries.append(pv)
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        minor_version=5,
        options=BASE_OPTIONS,
        subentries_data=subentries,
    )


async def _add_pv(hass: HomeAssistant, entry: MockConfigEntry):
    """Open the form for adding a PV system."""
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.solar_power", "0", {"unit_of_measurement": "W"})
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "pv_system"}
    )


async def _reconfigure_pv(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": PV_SUB_ID},
    )


def _sections(result) -> dict[str, tuple[dict, dict]]:
    """Return ``{section: ({field: suggested value}, section options)}``."""
    found = {}
    for key, value in result["data_schema"].schema.items():
        if str(key) in HISTORY_SECTIONS:
            found[str(key)] = (
                {
                    str(field): (field.description or {}).get("suggested_value")
                    for field in value.schema.schema
                },
                value.options,
            )
    assert found, "the form has no history sections"
    return found


# ---------------------------------------------------------------------------
# The sections
# ---------------------------------------------------------------------------


async def test_adding_a_device_offers_two_routes_collapsed(hass: HomeAssistant) -> None:
    """The form for a new PV system ends in two collapsed, optional sections,
    one per route: the kWh from the app, which Power Insight turns into
    money, and the amounts the app shows, taken as they are. A device set up
    with the grid shares the home's tariff, so it is not asked for one, nor
    for what went into batteries.
    """
    sections = _sections(await _add_pv(hass, _entry()))

    energy, energy_options = sections[HISTORY_ENERGY]
    amounts, amounts_options = sections[HISTORY_AMOUNTS]
    assert set(energy) == {"produced", "fed_in", "feed_in_tariff"}
    assert set(amounts) == {"savings", "export_compensation", "levelized_savings"}
    assert energy_options["collapsed"] is True
    assert amounts_options["collapsed"] is True


async def test_a_device_added_later_is_asked_for_its_own_tariff(
    hass: HomeAssistant,
) -> None:
    """Added two weeks after the grid, the PV system stands alone: the
    home's figures describe a period it was not part of, so the energy route
    also asks for its average tariff and what it charged batteries with.
    """
    two_weeks_ago = (dt_util.utcnow() - timedelta(days=14)).isoformat()
    energy, _ = _sections(await _add_pv(hass, _entry(grid_since=two_weeks_ago)))[HISTORY_ENERGY]
    assert {"average_tariff", "into_batteries"} <= set(energy)


async def test_adding_a_device_stores_its_history(hass: HomeAssistant) -> None:
    """Both routes are stored together on the subentry as entered (the
    frontend leaves empty fields out), next to the moment counting starts.
    """
    entry = _entry(grid_history={"home_fed_in": 4000.0, "average_tariff": 0.34})
    result = await _add_pv(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            **PV_INPUT,
            HISTORY_ENERGY: {"produced": 10000.0},
            HISTORY_AMOUNTS: {"savings": 1500.0},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    (pv,) = [s for s in entry.subentries.values() if s.title == "Rooftop Solar"]
    assert pv.data["history"] == {"produced": 10000.0, "savings": 1500.0}
    assert "counting_since" in pv.data


async def test_adding_a_device_without_history_stores_none(hass: HomeAssistant) -> None:
    """Untouched sections store nothing."""
    entry = _entry()
    result = await _add_pv(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={**PV_INPUT, HISTORY_ENERGY: {}, HISTORY_AMOUNTS: {}},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    (pv,) = [s for s in entry.subentries.values() if s.title == "Rooftop Solar"]
    assert "history" not in pv.data


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


async def test_figures_that_cannot_balance_are_refused(hass: HomeAssistant) -> None:
    """A PV system cannot export more than it produced. The form is shown
    again with the error naming the device and the figures as typed, and
    nothing is created.
    """
    entry = _entry()
    result = await _add_pv(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={**PV_INPUT, HISTORY_ENERGY: {"produced": 1000.0, "fed_in": 2000.0}},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": history.ERROR_FED_IN_EXCEEDS_OUTPUT}
    assert result["description_placeholders"]["history_device"] == "Rooftop Solar"
    energy, options = _sections(result)[HISTORY_ENERGY]
    assert energy["produced"] == 1000.0
    assert options["collapsed"] is False
    assert len(entry.subentries) == 1


async def test_a_form_is_checked_against_the_other_devices(hass: HomeAssistant) -> None:
    """The grid's home figures say 1,000 kWh were exported; the PV system's
    own export of 2,000 cannot fit in that. The problem is the home's figure,
    so the error names the grid.
    """
    entry = _entry(grid_history={"home_fed_in": 1000.0, "average_tariff": 0.34},
                   pv_history={"produced": 10000.0})
    result = await _reconfigure_pv(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            **_PV_RECONFIGURE,
            HISTORY_ENERGY: {"produced": 10000.0, "fed_in": 2000.0},
        },
    )

    assert result["errors"] == {"base": history.ERROR_FED_IN_EXCEEDS_HOME}
    assert result["description_placeholders"]["history_device"] == "Grid"
    assert entry.subentries[PV_SUB_ID].data["history"] == {"produced": 10000.0}


# ---------------------------------------------------------------------------
# Reconfigure
# ---------------------------------------------------------------------------

_PV_RECONFIGURE = {
    "power_entity": "sensor.pv_power",
    "power_entity_inverted": False,
    "exports_power": True,
    "export_compensation": 0.08,
}


async def test_reconfigure_shows_the_stored_history(hass: HomeAssistant) -> None:
    """Reconfigure suggests the stored figures, each in its route, and
    expands only the route that has some.
    """
    result = await _reconfigure_pv(hass, _entry(pv_history={"produced": 10000.0}))
    sections = _sections(result)
    energy, energy_options = sections[HISTORY_ENERGY]
    amounts, amounts_options = sections[HISTORY_AMOUNTS]
    assert energy["produced"] == 10000.0
    assert amounts["savings"] is None
    assert energy_options["collapsed"] is False
    assert amounts_options["collapsed"] is True


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        pytest.param(
            {HISTORY_ENERGY: {"produced": 9000.0}, HISTORY_AMOUNTS: {}},
            {"produced": 9000.0},
            id="changed",
        ),
        pytest.param(
            {HISTORY_ENERGY: {}, HISTORY_AMOUNTS: {}}, None, id="cleared",
        ),
        pytest.param({}, {"produced": 10000.0, "savings": 1500.0}, id="sections-not-sent"),
        pytest.param(
            {HISTORY_AMOUNTS: {"savings": 1200.0}},
            {"produced": 10000.0, "savings": 1200.0},
            id="only-one-route-sent",
        ),
    ],
)
async def test_reconfigure_saves_the_history(
    hass: HomeAssistant, submitted: dict, expected: dict | None
) -> None:
    """Saving replaces each route the form carried with its figures; an
    emptied form removes the history; a route the form did not carry keeps
    what was stored.
    """
    entry = _entry(pv_history={"produced": 10000.0, "savings": 1500.0})
    result = await _reconfigure_pv(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={**_PV_RECONFIGURE, **submitted}
    )

    assert result["type"] == FlowResultType.ABORT
    assert entry.subentries[PV_SUB_ID].data.get("history") == expected


async def test_the_grid_asks_for_the_homes_figures(hass: HomeAssistant) -> None:
    """The grid's sections hold the whole home's figures, by route."""
    entry = _entry()
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": GRID_SUB_ID},
    )
    sections = _sections(result)
    for name, by_type in HISTORY_SECTIONS.items():
        assert set(sections[name][0]) == set(by_type["grid"])


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------


def _load(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", TRANSLATION_FILES)
@pytest.mark.parametrize("step", ["configure", "reconfigure"])
@pytest.mark.parametrize("name", list(HISTORY_SECTIONS))
def test_every_history_field_is_labelled(path: str, step: str, name: str) -> None:
    """Every field a section can show has a label and a description in
    both forms, so none renders as its raw key.
    """
    texts = _load(path)["config_subentries"]["adapter"]["step"][step]["sections"][name]
    fields = {key for keys in HISTORY_SECTIONS[name].values() for key in keys}
    assert texts["name"] and texts["description"]
    assert fields <= set(texts["data"])
    assert fields <= set(texts["data_description"])


@pytest.mark.parametrize("path", TRANSLATION_FILES)
def test_the_history_wording_says_export(path: str) -> None:
    """The sections use the integration's own word for energy sent to the
    grid, "export", never "feed-in".
    """
    steps = _load(path)["config_subentries"]["adapter"]["step"]
    texts = json.dumps([steps[s]["sections"] for s in ("configure", "reconfigure")])
    errors = json.dumps(_load(path)["config_subentries"]["adapter"]["error"])
    for text in (texts, errors):
        assert "feed-in" not in text.lower() and "fed in" not in text.lower()


@pytest.mark.parametrize("path", TRANSLATION_FILES)
def test_every_history_refusal_has_a_message(path: str) -> None:
    """Every refusal ``history.solve`` can return has a form error text."""
    errors = _load(path)["config_subentries"]["adapter"]["error"]
    codes = {
        value for name, value in vars(history).items()
        if name.startswith("ERROR_")
    }
    assert codes <= set(errors)
