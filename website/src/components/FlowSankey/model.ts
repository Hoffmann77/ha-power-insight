/**
 * One snapshot, as the chart sees it: who supplies, who draws, and every flow
 * between them — all of it read from the engine's published results.
 *
 * Three stages:
 *
 *   sources ── left links ──▶ channels ── right links ──▶ sinks
 *
 * - A **left link** is one source's power into one channel:
 *   `source_adapters_<channel>_power`, which is exactly what the
 *   "Production to grid" / "Discharge to home consumption" / "Import to …"
 *   sensors show.
 * - A **right link** is one source's power into one sink:
 *   `sink_adapters_source_power` — the "Power from {source}" sensors. The home
 *   base load has no such property, so its links are its stored shares
 *   multiplied by its stored size: the only figure here the browser computes.
 *
 * Roles are not stored: a device is a source or a sink by the sign of its
 * reading, so the same grid is a source in one snapshot and a sink in the next.
 *
 * When the meters disagree (`metering_imbalance` > 0) the engine balances the
 * readings — sources move up, sinks down — and the flows follow the balanced
 * values. Each device's gap between its raw reading and its balanced flow is
 * kept as `unexplained`; across the snapshot those gaps add up to the
 * imbalance.
 */
import {abs, div, frac, isZero, mul, sub, sum, ZERO, type Frac} from './fraction';
import type {
  AdapterConfig,
  Channel,
  DeviceKind,
  PropertyCatalog,
  ReferenceCase,
  CaseState,
  SensorMap,
  ValueTree,
} from './types';

export const CHANNELS: Channel[] = ['export', 'consumption', 'charging', 'standby'];

export const CHANNEL_TITLE: {[k in Channel]: string} = {
  export: 'Grid export',
  consumption: 'Home consumption',
  charging: 'Battery charging',
  standby: 'System standby',
};

export type Basis = 'market' | 'levelized';

export type Role = 'source' | 'sink' | 'idle' | 'unavailable';

export interface Device {
  uid: string;
  kind: DeviceKind;
  config: AdapterConfig;
  /** The raw reading, signed. Null when unavailable (or no base load published). */
  reading: Frac | null;
  role: Role;
  /** The channel a sink draws through. */
  channel: Channel | null;
  /** Power through the device after the engine balanced the books. */
  flow: Frac;
  /** Reading and balanced flow disagree by this much (only with an imbalance). */
  unexplained: Frac;
  /** CSS colour, a palette token so it follows the theme. */
  color: string;
  /** "battery", "non-exporting", "unmetered" … */
  role_text: string;
}

export interface LeftLink {
  id: string;
  src: string;
  channel: Channel;
  w: Frac;
  /** Of the source's output — the `… ratio` sensor. */
  ratio: Frac | null;
  /** Of the channel — the `Share of …` sensor. */
  share: Frac | null;
}

export interface RightLink {
  id: string;
  src: string;
  channel: Channel;
  sink: string;
  w: Frac;
  /** True for the home base load, whose watts are share × size. */
  derived: boolean;
  /** Of the source's output (derived). */
  ofSource: Frac | null;
  /** Of the sink's draw — the provenance share. */
  ofSink: Frac | null;
}

export interface ChannelNode {
  id: Channel;
  w: Frac;
  /** Of gross power — the `… ratio` sensor on the whole-home device. */
  ofGross: Frac | null;
}

/** A sink drawing from a source its restriction does not allow. */
export interface BrokenRestriction {
  sink: string;
  src: string;
  w: Frac;
}

export interface Snapshot {
  caseTitle: string;
  index: number;
  state: CaseState;
  devices: Device[];
  sources: Device[];
  sinks: Device[];
  idle: Device[];
  unavailable: Device[];
  channels: ChannelNode[];
  left: LeftLink[];
  right: RightLink[];
  gross: Frac | null;
  imbalance: Frac | null;
  /** False when the engine publishes no provenance (an unavailable reading). */
  provenance: boolean;
  broken: BrokenRestriction[];
  values: Map<string, ValueTree>;
  catalog: PropertyCatalog;
  sensors: SensorMap;
}

// ---- reading the results -------------------------------------------------

type Tree = {[k: string]: ValueTree};

function at(values: Map<string, ValueTree>, property: string, ...keys: string[]) {
  let v: ValueTree | undefined = values.get(property);
  for (const k of keys) {
    if (v === null || v === undefined || typeof v !== 'object') {
      return null;
    }
    v = (v as Tree)[k];
  }
  return typeof v === 'string' ? frac(v) : null;
}

/** A stored value, exact. Null when absent or not published. */
export function value(s: Snapshot, property: string, ...keys: string[]): Frac | null {
  return at(s.values, property, ...keys);
}

// ---- ordering and colour -------------------------------------------------

const KIND_RANK: {[k in DeviceKind]: number} = {
  grid: 0,
  pv: 1,
  battery: 2,
  consumer: 3,
  home: 4,
};

/** A sink's channel, by what kind of device is drawing. */
export function sinkChannel(kind: DeviceKind): Channel {
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

const PALETTE_SLOT: {[k in DeviceKind]: string} = {
  grid: 'grid',
  pv: 'pv',
  battery: 'bat',
  consumer: 'con',
  home: 'home',
};

function roleText(kind: DeviceKind, role: Role, config: AdapterConfig): string {
  if (role === 'unavailable') {
    return 'unavailable';
  }
  switch (kind) {
    case 'grid':
      return role === 'sink' ? 'export' : role === 'source' ? 'import' : 'grid';
    case 'pv':
      return role === 'sink' ? 'PV standby' : 'PV string';
    case 'battery':
      if (role === 'sink') {
        return config.charge_from_adapters?.length ? 'restricted charging' : 'charging';
      }
      return config.exports_power === false ? 'non-exporting' : 'battery';
    case 'consumer':
      return config.power_from_adapters?.length ? 'restricted consumer' : 'consumer';
    default:
      return 'unmetered';
  }
}

// ---- building ------------------------------------------------------------

export function buildSnapshot(
  c: ReferenceCase,
  st: CaseState,
  catalog: PropertyCatalog,
  sensors: SensorMap,
): Snapshot {
  const values = new Map<string, ValueTree>(st.results.map((r) => [r.property, r.value]));
  const provenance = values.get('sink_adapters_source_shares') != null;
  const imbalance = at(values, 'metering_imbalance');
  const gross = at(values, 'gross_power');
  const hbl = at(values, 'home_base_load_power');

  const seen: {[k: string]: number} = {};
  const devices: Device[] = c.topology.map((d) => {
    const i = (seen[d.kind] = (seen[d.kind] ?? -1) + 1);
    const reading = frac(st.readings[d.uid]);
    const role: Role =
      reading === null ? 'unavailable' : reading.n > 0n ? 'source' : reading.n < 0n ? 'sink' : 'idle';
    return {
      uid: d.uid,
      kind: d.kind,
      config: d.config,
      reading,
      role,
      channel: role === 'sink' ? sinkChannel(d.kind) : null,
      flow: ZERO,
      unexplained: ZERO,
      color: `var(--fs-${PALETTE_SLOT[d.kind]}${d.kind === 'grid' ? '' : `-${i % 3}`})`,
      role_text: roleText(d.kind, role, d.config),
    };
  });
  // The unmetered rest of consumption. Drawn whenever the engine publishes a
  // size for it, and never with a fabricated zero when it does not.
  if (hbl !== null && hbl.n > 0n) {
    devices.push({
      uid: 'home',
      kind: 'home',
      config: {},
      reading: {n: -hbl.n, d: hbl.d},
      role: 'sink',
      channel: 'consumption',
      flow: ZERO,
      unexplained: ZERO,
      color: 'var(--fs-home)',
      role_text: 'unmetered',
    });
  }

  const topoRank = new Map(devices.map((d, i) => [d.uid, i]));
  const byKind = (a: Device, b: Device) =>
    KIND_RANK[a.kind] - KIND_RANK[b.kind] || topoRank.get(a.uid)! - topoRank.get(b.uid)!;
  const sources = devices.filter((d) => d.role === 'source').sort(byKind);
  const sinks = devices
    .filter((d) => d.role === 'sink')
    .sort(
      (a, b) =>
        CHANNELS.indexOf(a.channel!) - CHANNELS.indexOf(b.channel!) || byKind(a, b),
    );

  const left: LeftLink[] = [];
  const right: RightLink[] = [];
  if (provenance) {
    for (const s of sources) {
      for (const ch of CHANNELS) {
        const w = at(values, `source_adapters_${ch}_power`, s.uid);
        if (w && w.n > 0n) {
          left.push({
            id: `L:${s.uid}:${ch}`,
            src: s.uid,
            channel: ch,
            w,
            ratio: at(values, `source_adapters_${ch}_ratios`, s.uid),
            share: at(values, `source_adapters_${ch}_shares`, s.uid),
          });
        }
      }
    }
    for (const k of sinks) {
      for (const s of sources) {
        let w: Frac | null;
        let ofSink: Frac | null;
        if (k.uid === 'home') {
          ofSink = at(values, 'home_base_load_source_shares', s.uid);
          w = ofSink && hbl ? mul(ofSink, hbl) : null;
        } else {
          ofSink = at(values, 'sink_adapters_source_shares', k.uid, s.uid);
          w = at(values, 'sink_adapters_source_power', k.uid, s.uid);
        }
        if (w && w.n > 0n) {
          right.push({
            id: `R:${s.uid}:${k.uid}`,
            src: s.uid,
            channel: k.channel!,
            sink: k.uid,
            w,
            derived: k.uid === 'home',
            ofSource: null,
            ofSink,
          });
        }
      }
    }
  }

  for (const s of sources) {
    s.flow = sum(left.filter((l) => l.src === s.uid).map((l) => l.w));
  }
  for (const k of sinks) {
    k.flow = sum(right.filter((r) => r.sink === k.uid).map((r) => r.w));
  }
  for (const r of right) {
    const src = sources.find((s) => s.uid === r.src)!;
    r.ofSource = isZero(src.flow) ? null : div(r.w, src.flow);
  }
  // A reading the balanced flows do not account for. Only meaningful when
  // the engine reports an imbalance; with balanced books every gap is zero.
  if (imbalance && imbalance.n > 0n) {
    for (const d of [...sources, ...sinks]) {
      const gap = sub(abs(d.reading!), d.flow);
      d.unexplained = abs(gap);
    }
  }

  const channels: ChannelNode[] = CHANNELS.map((ch) => ({
    id: ch,
    w: sum(left.filter((l) => l.channel === ch).map((l) => l.w)),
    ofGross: at(values, `gross_power_${ch}_ratio`),
  })).filter((ch) => ch.w.n > 0n);

  // Power reaching a sink from a source its configuration rules out — the
  // engine relaxes a restriction the readings cannot satisfy, and says so by
  // where it routes the power.
  const broken: BrokenRestriction[] = [];
  for (const r of right) {
    const sink = devices.find((d) => d.uid === r.sink)!;
    const src = devices.find((d) => d.uid === r.src)!;
    const allowed =
      sink.kind === 'battery'
        ? sink.config.charge_from_adapters
        : sink.kind === 'consumer'
          ? sink.config.power_from_adapters
          : undefined;
    const ruledOut =
      (allowed && allowed.length > 0 && !allowed.includes(r.src)) ||
      (sink.kind === 'grid' && src.config.exports_power === false);
    if (ruledOut) {
      broken.push({sink: r.sink, src: r.src, w: r.w});
    }
  }

  return {
    caseTitle: c.title,
    index: c.states.indexOf(st),
    state: st,
    devices,
    sources,
    sinks,
    idle: devices.filter((d) => d.role === 'idle'),
    unavailable: devices.filter((d) => d.role === 'unavailable'),
    channels,
    left,
    right,
    gross,
    imbalance,
    provenance,
    broken,
    values,
    catalog,
    sensors,
  };
}

/** Whether `source` may ever feed `sink`, by configuration alone. */
export function allowed(s: Snapshot, src: string, sink: string): boolean {
  const k = s.devices.find((d) => d.uid === sink)!;
  const d = s.devices.find((x) => x.uid === src)!;
  if (k.kind === 'grid') {
    return d.config.exports_power !== false && d.kind !== 'grid';
  }
  const list =
    k.kind === 'battery'
      ? k.config.charge_from_adapters
      : k.kind === 'consumer'
        ? k.config.power_from_adapters
        : undefined;
  return !list || list.length === 0 || list.includes(src);
}

// ---- sensors -------------------------------------------------------------

export interface Named {
  /** The Home Assistant sensor's name, or the catalog title when no sensor reads it. */
  name: string;
  /** True when a Home Assistant sensor shows this value. */
  sensor: boolean;
  /** The engine property path, as a reader can look it up in the table. */
  path: string;
}

/** Name the value at `property[keys]` the way a reader meets it. */
export function named(
  s: Snapshot,
  device: DeviceKind | 'combined',
  property: string,
  keys: string[] = [],
  source?: string,
): Named {
  const candidates = s.sensors.sensors.filter((x) => x.property === property && !x.accumulates);
  const hit =
    candidates.find((x) => x.device === device) ??
    (device === 'combined' ? undefined : candidates.find((x) => x.device === 'combined'));
  const path = `${property}${keys.map((k) => `[${k}]`).join('')}`;
  if (hit) {
    return {name: hit.name.replace('{source}', source ?? 'source'), sensor: true, path};
  }
  return {name: s.catalog.properties[property]?.title ?? property, sensor: false, path};
}

// ---- money ---------------------------------------------------------------

export interface Money {
  value: Frac | null;
  named: Named;
}

function money(
  s: Snapshot,
  device: DeviceKind | 'combined',
  property: string,
  keys: string[] = [],
  source?: string,
): Money {
  return {value: value(s, property, ...keys), named: named(s, device, property, keys, source)};
}

/**
 * The euro figure a node carries in the €/h view. Every one is an engine
 * value read as published — nothing is priced in the browser — and the basis
 * switch re-reads a different family rather than recomputing.
 */
export function nodeMoney(s: Snapshot, d: Device, basis: Basis): Money | null {
  const lev = basis === 'levelized';
  if (d.role === 'source') {
    if (d.kind === 'grid') {
      return money(s, 'grid', 'source_adapters_coe_rate', [d.uid]);
    }
    return money(
      s,
      d.kind,
      lev ? 'adapters_levelized_saving_rates_corrected' : 'adapters_saving_rates',
      [d.uid],
    );
  }
  switch (d.kind) {
    case 'home':
      return money(s, 'home', 'home_base_load_avoided_cost_rate');
    case 'consumer':
      return money(s, 'consumer', lev ? 'sink_adapters_lcoo_rates' : 'sink_adapters_coo_rates', [
        d.uid,
      ]);
    case 'grid':
      return lev
        ? money(s, 'grid', 'sink_adapters_lcoo_rates', [d.uid])
        : money(s, 'grid', 'combined_export_compensation_rate');
    default:
      return money(
        s,
        d.kind,
        lev ? 'source_adapters_lcoo_rates_corrected' : 'source_adapters_coo_rates',
        [d.uid],
      );
  }
}

const CHANNEL_MONEY: {[k in Channel]: {market: string | null; levelized: string}} = {
  export: {market: 'combined_export_compensation_rate', levelized: 'combined_levelized_export_cost_rate'},
  consumption: {
    market: 'combined_consumption_cost_rate',
    levelized: 'combined_levelized_consumption_cost_rate',
  },
  charging: {market: 'combined_charging_cost_rate', levelized: 'combined_lcoo_rate_corrected'},
  standby: {market: null, levelized: 'combined_levelized_standby_cost_rate'},
};

export function channelMoney(s: Snapshot, ch: Channel, basis: Basis): Money | null {
  const property = CHANNEL_MONEY[ch][basis];
  return property ? money(s, 'combined', property) : null;
}

/** A link's own euro figure, where the engine publishes one. */
export function leftMoney(s: Snapshot, l: LeftLink): Money | null {
  if (l.channel !== 'export') {
    return null;
  }
  const kind = s.devices.find((d) => d.uid === l.src)!.kind;
  return money(s, kind, 'source_adapters_export_compensation_rates', [l.src]);
}

export function rightMoney(s: Snapshot, r: RightLink, basis: Basis): Money | null {
  const sink = s.devices.find((d) => d.uid === r.sink)!;
  if (sink.kind !== 'consumer' || basis !== 'market') {
    return null;
  }
  return money(s, 'consumer', 'sink_adapters_source_avoided_cost_rates', [r.sink, r.src], r.src);
}

export function deviceOf(s: Snapshot, uid: string): Device {
  return s.devices.find((d) => d.uid === uid)!;
}

