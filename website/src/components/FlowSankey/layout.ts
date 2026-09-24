/**
 * Lays out one snapshot as a three-column Sankey: sources → channels → sinks.
 *
 * Every figure except one is read straight from the engine's results:
 *
 *   - **source → channel** links are `source_adapters_<channel>_power`, the
 *     same values the "Production to …" / "Discharge to …" / "Import to …"
 *     sensors show.
 *   - **channel → sink** ribbons are per (source, sink) pair, multiplied out of
 *     the provenance matrix exactly as the current diagram does
 *     (`share × |reading|`). They keep the source's colour, so a sink's
 *     ribbon bundle *is* its provenance.
 *
 * The channel column is where the engine mixes: every source's link into a
 * channel ends there, and the sinks draw from it. Both sides of a channel add
 * up to the same watts when the engine's books balance. A channel whose sides
 * disagree is still drawn, with the taller side setting its height, so a
 * mismatch shows up as a visible step rather than being hidden.
 */
import {rat} from '../CaseDiagram/rational';
import type {
  AdapterKind,
  CaseState,
  ReferenceCase,
  Result,
  ValueTree,
} from '../CaseDiagram/types';
import {CHANNELS, type Channel} from './sensors';

export type NodeKind = AdapterKind | 'home';

export interface SNode {
  id: string;
  /** Fill for a device: its kind's colour, shaded per device within a kind. */
  color: string;
  column: 0 | 1 | 2;
  kind: NodeKind | 'channel';
  channel?: Channel;
  /** Watts through the node. */
  w: number;
  x: number;
  y: number;
  h: number;
}

export interface SLink {
  id: string;
  /** The source device the power came from; decides the colour. */
  source: string;
  sourceKind: NodeKind;
  color: string;
  from: string;
  to: string;
  channel: Channel;
  w: number;
  /** Stored exact value behind `w` (a watt figure or a share), for tooltips. */
  stored: string;
  /** y extent where the ribbon leaves `from` and where it enters `to`. */
  y0: number;
  y1: number;
  thickness: number;
  segment: 'left' | 'right';
}

export interface SankeyModel {
  nodes: SNode[];
  links: SLink[];
  idle: {uid: string; kind: NodeKind}[];
  byProperty: Map<string, ValueTree>;
  height: number;
  /** px per watt. */
  scale: number;
}

export const WIDTH = 920;
export const NODE_W = 14;
export const COL_X = [190, 453, 716];
const TOP = 62;
const BODY = 330;
const GAP = [18, 40, 18];
/** Visible minimum so a 5 W standby flow still reads as a ribbon. */
const MIN_PX = 1.5;

const KIND_ORDER: {[k in NodeKind]: number} = {
  grid: 0,
  pv: 1,
  battery: 2,
  consumer: 3,
  home: 4,
};

/** Which channel a sink belongs to, by what kind of device is drawing. */
export function sinkChannel(kind: NodeKind): Channel {
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

function asMap(v: ValueTree | undefined): {[k: string]: string | null} {
  return v && typeof v === 'object' ? (v as {[k: string]: string | null}) : {};
}

/**
 * Two batteries are both "battery", but their ribbons have to be told apart:
 * the first device of a kind keeps the kind colour, later ones are mixed
 * toward the text colour, which darkens in light mode and lightens in dark.
 */
export function deviceColors(c: ReferenceCase): Map<string, string> {
  const seen: {[k: string]: number} = {};
  const out = new Map<string, string>([['home', 'var(--cd-c-home)']]);
  for (const d of c.topology) {
    const i = (seen[d.kind] = (seen[d.kind] ?? -1) + 1);
    const base = `var(--cd-c-${d.kind})`;
    out.set(d.uid, i === 0 ? base : `color-mix(in srgb, ${base} ${Math.max(70 - 25 * (i - 1), 25)}%, var(--cd-fg))`);
  }
  return out;
}

export function lookup(
  byProperty: Map<string, ValueTree>,
  property: string,
  key?: string,
): string | null | undefined {
  const v = byProperty.get(property);
  if (key === undefined) {
    return typeof v === 'object' ? undefined : v;
  }
  if (v === null) {
    return null;
  }
  return asMap(v)[key];
}

export function buildSankey(c: ReferenceCase, st: CaseState): SankeyModel {
  const byProperty = new Map<string, ValueTree>(
    st.results.map((r: Result) => [r.property, r.value]),
  );
  const kindOf = new Map<string, NodeKind>(c.topology.map((d) => [d.uid, d.kind]));
  kindOf.set('home', 'home');
  const colors = deviceColors(c);

  const sources: string[] = [];
  const sinks: string[] = [];
  const idle: {uid: string; kind: NodeKind}[] = [];
  for (const d of c.topology) {
    const r = rat(st.readings[d.uid] ?? '0');
    if (st.readings[d.uid] === null) {
      idle.push({uid: d.uid, kind: d.kind});
    } else if (r > 0) {
      sources.push(d.uid);
    } else if (r < 0) {
      sinks.push(d.uid);
    } else {
      idle.push({uid: d.uid, kind: d.kind});
    }
  }
  const hbl = rat((lookup(byProperty, 'home_base_load_power') as string) ?? '0');
  if (hbl > 0) {
    sinks.push('home');
  }

  const kindRank = (u: string) => KIND_ORDER[kindOf.get(u) ?? 'consumer'];
  sources.sort((a, b) => kindRank(a) - kindRank(b));
  const chRank = (u: string) => CHANNELS.indexOf(sinkChannel(kindOf.get(u)!));
  sinks.sort((a, b) => chRank(a) - chRank(b) || kindRank(a) - kindRank(b));

  // source → channel, straight from the engine.
  type Raw = Omit<SLink, 'y0' | 'y1' | 'thickness'>;
  const left: Raw[] = [];
  for (const src of sources) {
    for (const ch of CHANNELS) {
      const stored = lookup(byProperty, `source_adapters_${ch}_power`, src);
      const w = rat(stored);
      if (w > 0) {
        left.push({
          id: `${src}>${ch}`,
          source: src,
          sourceKind: kindOf.get(src)!,
          color: colors.get(src)!,
          from: src,
          to: `ch:${ch}`,
          channel: ch,
          w,
          stored: stored!,
          segment: 'left',
        });
      }
    }
  }

  // channel → sink, one ribbon per source so provenance stays visible.
  const matrix = byProperty.get('sink_adapters_source_shares');
  const right: Raw[] = [];
  for (const sink of sinks) {
    const ch = sinkChannel(kindOf.get(sink)!);
    const row =
      sink === 'home'
        ? asMap(byProperty.get('home_base_load_source_shares'))
        : asMap(asMap(matrix as ValueTree)[sink] as unknown as ValueTree);
    const magnitude = sink === 'home' ? hbl : Math.abs(rat(st.readings[sink]));
    for (const src of sources) {
      const share = row[src];
      const w = rat(share) * magnitude;
      if (w > 0) {
        right.push({
          id: `${src}>${sink}`,
          source: src,
          sourceKind: kindOf.get(src)!,
          color: colors.get(src)!,
          from: `ch:${ch}`,
          to: sink,
          channel: ch,
          w,
          stored: share!,
          segment: 'right',
        });
      }
    }
  }

  // Node sizes: the larger of what flows in and what flows out.
  const inW = new Map<string, number>();
  const outW = new Map<string, number>();
  for (const l of [...left, ...right]) {
    outW.set(l.from, (outW.get(l.from) ?? 0) + l.w);
    inW.set(l.to, (inW.get(l.to) ?? 0) + l.w);
  }
  const channels = CHANNELS.filter(
    (ch) => (inW.get(`ch:${ch}`) ?? 0) > 0 || (outW.get(`ch:${ch}`) ?? 0) > 0,
  );
  const columns: {id: string; kind: SNode['kind']; channel?: Channel}[][] = [
    sources.map((u) => ({id: u, kind: kindOf.get(u)!})),
    channels.map((ch) => ({id: `ch:${ch}`, kind: 'channel' as const, channel: ch})),
    sinks.map((u) => ({id: u, kind: kindOf.get(u)!})),
  ];
  const weight = (id: string) => Math.max(inW.get(id) ?? 0, outW.get(id) ?? 0);
  const totals = columns.map((col) => col.reduce((a, n) => a + weight(n.id), 0));
  const scale = Math.max(...totals) > 0 ? BODY / Math.max(...totals) : 0;

  const colH = columns.map(
    (col, ci) =>
      col.reduce((a, n) => a + Math.max(weight(n.id) * scale, MIN_PX), 0) +
      GAP[ci] * Math.max(col.length - 1, 0),
  );
  const maxH = Math.max(...colH);
  const nodes: SNode[] = [];
  let height = TOP;
  columns.forEach((col, ci) => {
    // Centre every column on the tallest one.
    let y = TOP + (maxH - colH[ci]) / 2;
    for (const n of col) {
      const h = Math.max(weight(n.id) * scale, MIN_PX);
      nodes.push({
        id: n.id,
        column: ci as 0 | 1 | 2,
        kind: n.kind,
        channel: n.channel,
        color: n.channel ? `var(--fs-ch-${n.channel})` : colors.get(n.id)!,
        w: weight(n.id),
        x: COL_X[ci],
        y,
        h,
      });
      y += h + GAP[ci];
    }
    height = Math.max(height, y);
  });
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  // Stack ribbons on each side of each node. Order keeps crossings low:
  // leaving a source, by channel; entering a channel, by source; leaving a
  // channel, by sink then source; entering a sink, by source.
  const srcRank = (u: string) => sources.indexOf(u);
  const sinkRank = (u: string) => sinks.indexOf(u);
  const outCursor = new Map<string, number>();
  const inCursor = new Map<string, number>();
  const place = (raw: Raw[], outKey: (l: Raw) => number, inKey: (l: Raw) => number) => {
    const placed = new Map<string, SLink>();
    for (const l of [...raw].sort((a, b) => outKey(a) - outKey(b))) {
      const t = Math.max(l.w * scale, 0.75);
      const n = nodeById.get(l.from)!;
      const y = outCursor.get(l.from) ?? n.y;
      outCursor.set(l.from, y + t);
      placed.set(l.id + l.segment, {...l, y0: y + t / 2, y1: 0, thickness: t});
    }
    for (const l of [...raw].sort((a, b) => inKey(a) - inKey(b))) {
      const p = placed.get(l.id + l.segment)!;
      const n = nodeById.get(l.to)!;
      const y = inCursor.get(l.to) ?? n.y;
      inCursor.set(l.to, y + p.thickness);
      p.y1 = y + p.thickness / 2;
    }
    return [...placed.values()];
  };
  const links = [
    ...place(
      left,
      (l) => srcRank(l.source) * 10 + CHANNELS.indexOf(l.channel),
      (l) => CHANNELS.indexOf(l.channel) * 100 + srcRank(l.source),
    ),
    ...place(
      right,
      (l) => CHANNELS.indexOf(l.channel) * 10000 + sinkRank(l.to) * 100 + srcRank(l.source),
      (l) => sinkRank(l.to) * 100 + srcRank(l.source),
    ),
  ];

  return {nodes, links, idle, byProperty, height: height + 8, scale};
}

/** A ribbon as a filled cubic band from one column to the next. */
export function ribbonPath(l: SLink): string {
  const x0 = COL_X[l.segment === 'left' ? 0 : 1] + NODE_W;
  const x1 = COL_X[l.segment === 'left' ? 1 : 2];
  const xm = (x0 + x1) / 2;
  const h = l.thickness / 2;
  return [
    `M${x0},${l.y0 - h}`,
    `C${xm},${l.y0 - h} ${xm},${l.y1 - h} ${x1},${l.y1 - h}`,
    `L${x1},${l.y1 + h}`,
    `C${xm},${l.y1 + h} ${xm},${l.y0 + h} ${x0},${l.y0 + h}`,
    'Z',
  ].join(' ');
}
