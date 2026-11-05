# Where the power comes from

How Power Insight decides which source powers what: the flow channels behind
the *ratio* and *share* sensors, and the rules that decide a battery's or
consumer's source mix. For the short version, see
[How it works](../how-it-works.md).

## The four channels

Gross power leaves the system through exactly four **channels**. Each channel
has a natural **sink** — the device type that receives that power:

| Abbrev | Channel | Sink device | Sensor wording |
|---|---|---|---|
| **EXP** | Export | Grid | *… to grid* |
| **CON** | Self-consumption | Consumers (loads) | *… to home consumption* |
| **CHG** | Charging | Batteries | *… to batteries* |
| **STB** | Standby | PV systems (their own night draw) | *… to system standby* |

"System standby" is the idle draw of the energy system's own equipment — not
household appliances on standby, which count as home consumption.

Every **provider** — the devices that *feed* gross power (grid import, PV
production, battery discharge) — expresses its relationship to a channel two
ways, alongside its power in Watts (*Production to home consumption*):

- **ratio** — of *this provider's own* output, the fraction going to the
  channel (`channel_power ÷ provider_output`) — *Production to home
  consumption ratio*.
- **share** — of *the whole channel's* power, the fraction *this provider*
  supplied (`provider_contribution ÷ channel_total`) — *Share of home
  consumption*.

Not every provider feeds every channel. The grid cannot export to itself, so it
has no EXP sensors; otherwise each provider carries a `_ratio` and a `_share`
for each channel it can feed:

| Provider | EXP | CON | CHG | STB |
|---|:--:|:--:|:--:|:--:|
| **Grid** | — | ✓ | ✓ | ✓ |
| **PV** | ✓ | ✓ | ✓ | ✓ |
| **Battery** | ✓ | ✓ | ✓ | ✓ |

CHG is the only channel with explicit routing (a battery's **Charges from**
list), so it has **two complementary sensor families** — don't confuse them:

- the provider-side aggregate **Share of battery charging** ("X % of *all* charging in the
  home is supplied by the grid"), on the grid/PV/battery device; and
- the sink-side per-source breakdown **Charging share from &lt;source&gt;**
  ("X % of *this battery's* charging comes from the grid"), on the battery — see
  [Charging-source attribution](#charging-source-attribution).

CHG sensors on a provider only appear when that provider is actually a
configured charge source for some battery; STB, having no routing, is
attributed to providers in proportion to their share of gross power.

## Charging-source attribution

When a battery charges, its stored energy comes from some mix of the grid and
your PV systems — configured in the battery's **Charges from** list. Power
Insight traces that mix in real time to:

- attribute the battery's charging cost to the right source, and
- power the **charging source share** sensors ("70 % solar, 30 % grid").

The same tracing decides where a smart-plug **consumer** restricted to specific
sources (its **Powered by** list) draws its power, and how the power you export
is sourced.

### How the mix is decided

Your local generation — solar production and battery discharge — is limited, and
while you are *importing* from the grid it is the scarce, cheaper resource. Power
Insight hands it out in a fixed priority order, and the grid fills whatever is
left over:

1. **Locked devices first.** A battery set to charge from *solar only*, or a
   smart plug that runs on *excess solar*, has no fallback — so it gets first
   claim on its allowed local sources.
2. **Your home base load next.** The always-on household consumption you don't
   meter directly takes the local power it needs before any flexible device
   does.
3. **Flexible devices last.** A battery allowed to charge from the grid *can*
   fall back on it, so it only receives the local generation the first two steps
   left behind; the grid covers the rest of its draw.

When you are *exporting* — your solar is in surplus — local power isn't scarce,
so this ordering doesn't apply and every device is simply attributed to the live
mix.

### Why two devices can show different mixes

Because local generation is allocated in order rather than split evenly, two
devices drawing power at the same instant can show different source mixes:

- A battery locked to solar shows **100 % solar** while any is available; a
  battery that can also use the grid, charging at the same moment, may show
  mostly **grid** — it receives only the solar the locked battery and your home
  load didn't take.
- The mix shifts with your **household load**: the more your home consumes
  directly, the less local generation reaches a flexible battery, so its grid
  share rises — even though nothing about the battery itself changed.
- Two PV systems of different sizes show it too: a battery drawing from the
  larger one keeps more solar (a lower grid share) than one drawing from the
  smaller, because more of the larger system survives the earlier steps.

Energy lost in a charge/discharge cycle needs no correction here: the battery's
charging and discharging are both metered at its AC port, so the losses are
already the difference between the two.

### When a device draws from outside its sources

The sources you pick under **Specific devices** describe what you *expect* your
energy manager to do. They are not a hard limit: Power Insight counts every watt
your meters report, even when it can't have come from the sources you picked.

So when a device draws more than its allowed sources supply at that moment, the
extra is counted as coming from your other sources. The typical case is a
battery set to charge from solar only that tops up from the grid at night: with
no solar to draw on, its whole charge is counted — and priced — as grid power.

The watts drawn from outside the selection are shown in the
`restriction_deficit` attribute of the device's *Operating cost rate* and
*Levelized operating cost rate* sensors. It reads `0` while the device sticks to
its sources, and exists only on devices set to **Specific devices**.

A deficit is not necessarily a mistake. A battery that prefers solar but tops up
from the grid when its charge runs low is still best set to solar only: with the
grid in its list, Power Insight would count its charging as grid power first
whenever your home imports. Set to solar only, its charging counts as solar
whenever there is solar, and the deficit shows just the grid top-ups — which is
what really happened.
A deficit that never goes away, on the other hand, usually means the selection
no longer matches what your energy manager does; **Reconfigure** the device.

:::info[The exact rules]

The precise allocation — the three tiers above and their edge cases — is
written up for contributors in
[Engine calculation decisions](../dev/engine-calculations.md).

:::
