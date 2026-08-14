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
import {rat} from './rational';
import type {
  AnchorCase,
  AnchorState,
  Certification,
  Expectation,
  Metric,
  NodeKind,
  Role,
  ValueTree,
} from './types';

export interface FlowNode {
  uid: string;
  kind: NodeKind;
  config: AnchorCase['topology'][number]['config'] | null;
  /** Signed watts as read (the virtual home node is stored negative). */
  reading: number;
  role: Role;
  /** Left column for sources, right for sinks. */
  side: 'L' | 'R';
  /** True for the home base load, which has no device behind it. */
  virtual: boolean;
}

export interface FlowEdge {
  from: string;
  to: string;
  /** Watts on this flow. */
  w: number;
  /** The share as stored, so the exact fraction survives to the UI. */
  share: string;
}

export interface FlowModel {
  nodes: FlowNode[];
  edges: FlowEdge[];
  deficits: {[uid: string]: string};
  /** uid -> €/kWh this source is charged at (grid tariff, or own LCOE/LCOS). */
  rates: {[uid: string]: number};
  gross: number;
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

export function indexExpectations(state: AnchorState): Map<string, Expectation> {
  return new Map(state.expectations.map((e) => [e.property, e]));
}

export function valueOf(
  byProperty: Map<string, Expectation>,
  property: string,
): ValueTree | undefined {
  return byProperty.get(property)?.value;
}

export function scalar(
  byProperty: Map<string, Expectation>,
  property: string,
): number {
  const v = valueOf(byProperty, property);
  return typeof v === 'string' ? rat(v) : 0;
}

export function certificationOf(
  byProperty: Map<string, Expectation>,
  property: string,
): Certification | undefined {
  return byProperty.get(property)?.certification;
}

export function isVerified(
  byProperty: Map<string, Expectation>,
  property: string,
): boolean {
  return certificationOf(byProperty, property)?.status === 'verified';
}

/** `[verified, total]` across every expectation in the case. */
export function certCounts(c: AnchorCase): [number, number] {
  let verified = 0;
  let total = 0;
  for (const st of c.states) {
    for (const e of st.expectations) {
      total += 1;
      if (e.certification.status === 'verified') {
        verified += 1;
      }
    }
  }
  return [verified, total];
}

export function buildModel(c: AnchorCase, st: AnchorState): FlowModel {
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
    };
  });

  // The unmetered home base load competes for power like any other sink, but
  // has no adapter — it exists only in its own properties.
  const hbl = scalar(byProperty, 'home_base_load_power');
  nodes.push({
    uid: 'home',
    kind: 'home',
    config: null,
    reading: -hbl,
    role: hbl > 0 ? 'sink' : 'idle',
    side: 'R',
    virtual: true,
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
    if (value > 0) {
      edges.push({from: src, to: 'home', w: value * hbl, share});
    }
  }

  const rates: {[uid: string]: number} = {};
  for (const d of c.topology) {
    rates[d.uid] =
      d.kind === 'grid'
        ? rat(st.price)
        : d.kind === 'pv'
          ? rat(d.config.lcoe ?? '0')
          : d.kind === 'battery'
            ? rat(d.config.lcos ?? '0')
            : 0;
  }

  return {
    nodes,
    edges,
    deficits: asMap(valueOf(byProperty, 'sink_adapters_restriction_deficit')),
    rates,
    gross: scalar(byProperty, 'gross_power'),
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
    return (Math.abs(n.reading) / 1000) * (m.rates[n.uid] ?? 0);
  }
  return m.edges
    .filter((e) => e.to === n.uid)
    .reduce((acc, e) => acc + (e.w / 1000) * (m.rates[e.from] ?? 0), 0);
}

/** The label a node carries under the current metric. */
export function nodeValueLabel(
  m: FlowModel,
  n: FlowNode,
  metric: Metric,
  fmtW: (v: number) => string,
  fmtEur: (v: number) => string,
): string {
  if (metric === 'power' || n.role === 'idle') {
    return fmtW(Math.abs(n.reading));
  }
  if (metric === 'shares') {
    return m.gross
      ? (Math.round((Math.abs(n.reading) / m.gross) * 100) / 100).toFixed(2)
      : '0';
  }
  return fmtEur(costOf(m, n));
}
