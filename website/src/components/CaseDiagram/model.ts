/**
 * Turns one (case, state) pair into the graph the diagram draws.
 *
 * Two things are derived rather than stored, because the case file keeps a
 * single source of truth:
 *
 *   - **Roles.** A device is a source or a sink according to the *sign* of its
 *     reading this snapshot, so the same grid is the largest source in one
 *     state and a restricted sink in the next.
 *   - **Edges.** Watts on a flow are `share × |sink draw|`, multiplied out of
 *     the provenance matrix rather than duplicated in the data.
 */
import {fmtEur, fmtPct, fmtW, rat} from './rational';
import type {
  Channel,
  Expectation,
  LayerId,
  NodeKind,
  ReferenceCase,
  CaseState,
  Role,
  ValueTree,
} from './types';

export interface FlowNode {
  uid: string;
  kind: NodeKind;
  config: ReferenceCase['topology'][number]['config'] | null;
  /**
   * Signed watts as read (the virtual home node is stored negative). Null on
   * the home node when its size has not been derived — a real device always
   * has a reading, because readings are inputs to the corpus rather than
   * answers in it.
   */
  reading: number | null;
  role: Role;
  /** Left column for sources, right for sinks. */
  side: 'L' | 'R';
  /** True for the home base load, which has no device behind it. */
  virtual: boolean;
  /** Which channel of the gross-power split this sink is, if it is one. */
  channel: Channel | null;
}

export interface FlowEdge {
  from: string;
  to: string;
  /** Watts on this flow. */
  w: number;
  /** The share as stored, so the exact fraction survives to the UI. */
  share: string;
}

/** One segment of the gross-power channel split. */
export interface ChannelSlice {
  channel: Channel;
  label: string;
  /** The stored ratio, exact. */
  ratio: string;
  value: number;
}

export interface FlowModel {
  nodes: FlowNode[];
  edges: FlowEdge[];
  deficits: {[uid: string]: string};
  /**
   * uid -> €/kWh this source is charged at. The engine's own per-source price
   * where the state publishes one, otherwise the static tariff or LCOE/LCOS —
   * so a browser-side cost never contradicts a published number.
   */
  rates: {[uid: string]: number};
  /** Null until somebody derives it. */
  gross: number | null;
  channels: ChannelSlice[];
  byProperty: Map<string, Expectation>;
}

/** Where an idle device sits when it has no flow to place it. */
const IDLE_SIDE: {[k in NodeKind]: 'L' | 'R'} = {
  grid: 'L',
  pv: 'L',
  battery: 'R',
  consumer: 'R',
  home: 'R',
};

/** The four channels gross power splits into, and the ratio that measures each. */
const CHANNEL_RATIOS: [Channel, string, string][] = [
  ['export', 'Export', 'gross_power_export_ratio'],
  ['consumption', 'Self-consumption', 'gross_power_consumption_ratio'],
  ['charging', 'Charging', 'gross_power_charging_ratio'],
  ['standby', 'Standby', 'gross_power_standby_ratio'],
];

export const CHANNEL_LABEL: {[k in Channel]: string} = {
  export: 'export',
  charging: 'charging',
  consumption: 'consumption',
  standby: 'standby',
};

function asMap(v: ValueTree | undefined): {[k: string]: string} {
  if (v === null || v === undefined || typeof v !== 'object') {
    return {};
  }
  const out: {[k: string]: string} = {};
  for (const [k, inner] of Object.entries(v)) {
    if (typeof inner === 'string') {
      out[k] = inner;
    }
  }
  return out;
}

function asNested(v: ValueTree | undefined): {[k: string]: {[k: string]: string}} {
  if (v === null || v === undefined || typeof v !== 'object') {
    return {};
  }
  const out: {[k: string]: {[k: string]: string}} = {};
  for (const [k, inner] of Object.entries(v)) {
    if (inner && typeof inner === 'object') {
      out[k] = asMap(inner);
    }
  }
  return out;
}

export function indexExpectations(state: CaseState): Map<string, Expectation> {
  return new Map(state.expectations.map((e) => [e.property, e]));
}

export function valueOf(
  byProperty: Map<string, Expectation>,
  property: string,
): ValueTree | undefined {
  return byProperty.get(property)?.value;
}

/**
 * A scalar property as a number, or `null` when the corpus has no answer.
 *
 * Null covers both nothings — a property this snapshot publishes no value for,
 * and one published as having no value — and the distinction does not matter
 * to a diagram, because in either case there is no number to draw and it must
 * not invent one. Returning 0 would draw an idle node reading "0 W", a claim
 * nobody made.
 */
export function scalar(
  byProperty: Map<string, Expectation>,
  property: string,
): number | null {
  const v = valueOf(byProperty, property);
  return typeof v === 'string' ? rat(v) : null;
}

/** Whether this snapshot publishes a value for `property` at all. */
export function hasValue(
  byProperty: Map<string, Expectation>,
  property: string,
): boolean {
  return byProperty.has(property);
}

/** How many values the case publishes across all its snapshots. */
export function derivedCount(c: ReferenceCase): number {
  return c.states.reduce((n, st) => n + st.expectations.length, 0);
}

/**
 * Which channel a sink is. The channel split is a property of what the power
 * was *used for*, and that is exactly what a sink's kind says: a grid being fed
 * is export, a battery taking power is charging, a PV string drawing is
 * standby, and everything else is self-consumption.
 */
function channelOf(kind: NodeKind, role: Role): Channel | null {
  if (role !== 'sink') {
    return null;
  }
  switch (kind) {
    case 'grid':
      return 'export';
    case 'battery':
      return 'charging';
    case 'pv':
      return 'standby';
    default:
      return 'consumption';
  }
}

export function buildModel(c: ReferenceCase, st: CaseState): FlowModel {
  const byProperty = indexExpectations(st);

  const nodes: FlowNode[] = c.topology.map((d) => {
    const reading = rat(st.readings[d.uid] ?? '0');
    const role: Role = reading > 0 ? 'source' : reading < 0 ? 'sink' : 'idle';
    return {
      uid: d.uid,
      kind: d.kind,
      config: d.config,
      reading,
      role,
      side: 'L',
      virtual: false,
      channel: channelOf(d.kind, role),
    };
  });

  // The unmetered home base load competes for power like any other sink, but
  // has no adapter — it exists only in its own properties.
  // Structural, so it is drawn whether or not anyone has derived its size —
  // but with no reading until they have, rather than a fabricated zero.
  const hbl = scalar(byProperty, 'home_base_load_power');
  nodes.push({
    uid: 'home',
    kind: 'home',
    config: null,
    reading: hbl === null ? null : -hbl,
    role: hbl !== null && hbl > 0 ? 'sink' : 'idle',
    side: 'R',
    virtual: true,
    channel: hbl !== null && hbl > 0 ? 'consumption' : null,
  });

  for (const n of nodes) {
    n.side = n.role === 'source' ? 'L' : n.role === 'sink' ? 'R' : IDLE_SIDE[n.kind];
  }

  const edges: FlowEdge[] = [];
  const shares = asNested(valueOf(byProperty, 'sink_adapters_source_shares'));
  for (const [sink, row] of Object.entries(shares)) {
    const magnitude = Math.abs(rat(st.readings[sink] ?? '0'));
    for (const [src, share] of Object.entries(row)) {
      const value = rat(share);
      if (value > 0) {
        edges.push({from: src, to: sink, w: value * magnitude, share});
      }
    }
  }
  const homeShares = asMap(valueOf(byProperty, 'home_base_load_source_shares'));
  for (const [src, share] of Object.entries(homeShares)) {
    const value = rat(share);
    if (value > 0 && hbl !== null) {
      edges.push({from: src, to: 'home', w: value * hbl, share});
    }
  }

  // Prefer the engine's own per-source price. It is published for exactly the
  // states where the static config would be the wrong answer — a discharging
  // battery is priced at its LCOS, not at the mix it charged on.
  const published = asMap(valueOf(byProperty, 'source_adapters_dynamic_lcoe'));
  const rates: {[uid: string]: number} = {};
  for (const d of c.topology) {
    if (published[d.uid] !== undefined) {
      rates[d.uid] = rat(published[d.uid]);
      continue;
    }
    rates[d.uid] =
      d.kind === 'grid'
        ? rat(st.price)
        : d.kind === 'pv'
          ? rat(d.config.lcoe ?? '0')
          : d.kind === 'battery'
            ? rat(d.config.lcos ?? '0')
            : 0;
  }

  const channels: ChannelSlice[] = [];
  for (const [channel, label, property] of CHANNEL_RATIOS) {
    const stored = valueOf(byProperty, property);
    if (typeof stored !== 'string') {
      continue;
    }
    const value = rat(stored);
    if (value > 0) {
      channels.push({channel, label, ratio: stored, value});
    }
  }

  return {
    nodes,
    edges,
    deficits: asMap(valueOf(byProperty, 'sink_adapters_restriction_deficit')),
    rates,
    gross: scalar(byProperty, 'gross_power'),
    channels,
    byProperty,
  };
}

/** What a device is doing this snapshot, in the engine's own vocabulary. */
export function roleText(n: FlowNode): string {
  if (n.virtual) {
    return n.role === 'sink' ? 'unmetered sink' : 'idle';
  }
  if (n.role === 'idle') {
    return 'idle';
  }
  if (n.kind === 'grid') {
    return n.role === 'source' ? 'importing → source' : 'exporting → restricted sink';
  }
  if (n.kind === 'pv') {
    return n.role === 'source' ? 'producing → source' : 'standby draw → sink';
  }
  if (n.kind === 'battery') {
    return n.role === 'source' ? 'discharging → source' : 'charging → sink';
  }
  return 'load → sink';
}

/** €/h a node accounts for: its own output priced, or its intake priced. */
export function costOf(m: FlowModel, n: FlowNode): number {
  if (n.role === 'source') {
    return ((n.reading === null ? 0 : Math.abs(n.reading)) / 1000) * (m.rates[n.uid] ?? 0);
  }
  return m.edges
    .filter((e) => e.to === n.uid)
    .reduce((acc, e) => acc + (e.w / 1000) * (m.rates[e.from] ?? 0), 0);
}

/**
 * The label a node carries under the current layer.
 *
 * Every layer answers a different question about the same node, so the graph is
 * re-labelled rather than redrawn: watts for the totals, a slice of gross power
 * for provenance and the channel split, and a cost rate for the monetary model.
 */
export function nodeValueLabel(
  m: FlowModel,
  n: FlowNode,
  layer: LayerId,
): string {
  switch (layer) {
    case '2':
      return m.gross && n.reading !== null
        ? fmtPct(Math.abs(n.reading) / m.gross)
        : '—';
    case '4':
      return fmtEur(costOf(m, n));
    default:
      return fmtW(n.reading === null ? null : Math.abs(n.reading));
  }
}

/** The same question, asked only of what a node exchanges with the selection. */
export function edgeSetLabel(
  m: FlowModel,
  edges: FlowEdge[],
  layer: LayerId,
): string {
  const watts = edges.reduce((acc, e) => acc + e.w, 0);
  switch (layer) {
    case '2':
      return edges.length
        ? fmtPct(edges.reduce((acc, e) => acc + rat(e.share), 0))
        : '—';
    case '4':
      return fmtEur(
        edges.reduce((acc, e) => acc + (e.w / 1000) * (m.rates[e.from] ?? 0), 0),
      );
    default:
      return fmtW(watts);
  }
}
