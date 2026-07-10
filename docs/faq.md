# FAQ

## How are savings calculated?

Power Insight recognises two ways your devices generate savings:

1. **Selling surplus energy to the grid** (export compensation).
2. **Replacing energy you would otherwise import** with energy from your own
   devices (self-consumption savings), valued at the grid price you avoided.

Total savings add both and subtract the costs your devices accumulate:

```
savings = export_compensation + self_consumption_savings − operating_costs
```

For PV systems the operating cost is mainly standby consumption at night; for
batteries it's the cost of the energy used to charge them. See
[How savings are calculated](concepts.md#how-savings-are-calculated).

## Why does my battery have negative savings?

Any device can show negative savings if it doesn't earn enough to cover its
costs — and a battery **always** shows negative savings while charging, because
Power Insight tracks the cost of the energy going into it. That cost turns into
positive savings when the battery later discharges and offsets a grid import.
See [the concepts page](concepts.md#why-does-my-battery-have-negative-savings).

## Does Power Insight work with dynamic electricity prices?

Yes — this is a core design goal. Every calculation uses the **current** value of
your grid price entity, so a live/dynamic tariff sensor works out of the box. No
energy meters or daily averaging are involved.

## Do I need energy (kWh) meters?

No. Power Insight is driven by **instantaneous power** sensors (W / kW / MW), not
energy meters. Each device and the grid connection must expose a power sensor.

## Can I track two grid connections?

Not within one config entry — a config entry models a single grid connection /
energy mix. Add a **second config entry** for a second grid connection.

## I enabled a cost/levelized sensor but it didn't appear. Why?

Those sensors need extra data. Cost sensors need an **electricity price entity**
on the grid; levelized sensors need **lifetime production and cost** on the
device. The options flow will name any device that's missing data and ask you to
**Reconfigure** it. See
[Sensors, presets & options](configuration/options-and-presets.md#missing-data-guard).

## Are there CO₂ sensors?

Not yet. CO₂ tracking is scaffolded — the config flow may ask for a CO₂ intensity
entity or footprint — but **no CO₂ sensors are created in this release**.

## If I turn a sensor off, do I lose its history?

No. Disabled sensors are hidden and stop updating, but their history is kept and
they return the moment you re-enable the option.

## How do I carry over historical totals?

Use the [`power_insight.set_value` service](services.md) to seed an accumulated
total sensor with a starting value.
