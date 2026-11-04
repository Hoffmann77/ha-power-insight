/**
 * Where everything sits: d3-sankey for the graph, the design's geometry on top.
 *
 * d3-sankey does the bookkeeping — which column a node is in, and the order
 * ribbons stack in at each node, which is what keeps them from crossing. Its
 * own vertical placement is replaced: the design fixes the scale (the tallest
 * column fills the body), gives each column its own gap, and centres every
 * column on the tallest. `sankey.update()` then re-derives every ribbon's ends
 * from those positions, which is the library's documented way to move nodes.
 *
 * Everything here is pure arithmetic — no DOM — so it runs during server
 * rendering and the chart arrives as finished SVG.
 *
 * Coordinates are abstract: `d` runs along the flow (source → sink) and `b`
 * across it. The wide layout draws `d` as x; the narrow one as y.
 */
import {sankey, type SankeyGraph, type SankeyLink, type SankeyNode} from 'd3-sankey';

import {num} from './fraction';
import {CHANNELS, type Snapshot} from './model';

export interface Geometry {
  /** Along the flow: where each column's bars start. */
  cols: [number, number, number];
  /** Bar thickness along the flow. */
  nodeW: number;
  /** Space across the flow that the tallest column's bars fill. */
  body: number;
  gaps: [number, number, number];
  /** Offset across the flow before the first bar. */
  start: number;
  /** Fit every column into `body` (narrow) instead of scaling to the tallest (wide). */
  fit: boolean;
  /** Total extent along and across the flow. */
  size: (breadth: number) => {w: number; h: number};
}

/**
 * The design's wide layout. The mockup is 880 wide; the docs column beside the
 * table of contents is narrower, so the canvas is tightened to 760 to keep its
 * 10 px labels legible at the size it is actually shown.
 */
export const WIDE: Geometry = {
  cols: [182, 381, 580],
  nodeW: 8,
  body: 280,
  gaps: [30, 56, 30],
  start: 66,
  fit: false,
  size: (breadth) => ({w: 760, h: Math.max(breadth + 40, 200)}),
};

/** Top-to-bottom for narrow screens: 360 wide, bars across. */
export const NARROW: Geometry = {
  cols: [74, 268, 462],
  nodeW: 8,
  body: 324,
  gaps: [18, 28, 18],
  start: 18,
  fit: true,
  size: () => ({w: 360, h: 548}),
};

const MIN_NODE = 1.5;

export interface LNode {
  id: string;
  column: 0 | 1 | 2;
  /** Device uid, or the channel id. */
  key: string;
  d0: number;
  d1: number;
  b0: number;
  b1: number;
  /** Across-the-flow size of the part of the bar the meters do not explain. */
  hatch: number;
}

export interface LLink {
  id: string;
  /** Source end and target end, across the flow, at the ribbon's centre. */
  b0: number;
  b1: number;
  /** Along the flow: where the ribbon leaves and arrives. */
  d0: number;
  d1: number;
  width: number;
}

export interface Layout {
  nodes: Map<string, LNode>;
  links: Map<string, LLink>;
  w: number;
  h: number;
  empty: boolean;
}

interface NodeIn {
  id: string;
  column: 0 | 1 | 2;
  key: string;
  watts: number;
  hatch: number;
}

interface LinkIn {
  id: string;
  source: string;
  target: string;
  value: number;
  /** Ordering keys. */
  side: 'left' | 'right';
  channel: number;
  src: number;
  sink: number;
}

type N = SankeyNode<NodeIn, LinkIn>;
type L = SankeyLink<NodeIn, LinkIn>;

export function layout(s: Snapshot, g: Geometry): Layout {
  const srcRank = new Map(s.sources.map((d, i) => [d.uid, i]));
  const sinkRank = new Map(s.sinks.map((d, i) => [d.uid, i]));

  // Bars are as long as the larger of reading and balanced flow, so the
  // unexplained part of a reading still has somewhere to be drawn.
  const deviceWatts = (d: (typeof s.devices)[number]) =>
    Math.max(Math.abs(num(d.reading)), num(d.flow));
  const nodes: NodeIn[] = [
    ...s.sources.map((d) => ({
      id: `S:${d.uid}`,
      column: 0 as const,
      key: d.uid,
      watts: deviceWatts(d),
      hatch: num(d.unexplained),
    })),
    ...s.channels.map((c) => ({
      id: `C:${c.id}`,
      column: 1 as const,
      key: c.id,
      watts: Math.max(
        num(c.w),
        s.right.filter((r) => r.channel === c.id).reduce((a, r) => a + num(r.w), 0),
      ),
      hatch: 0,
    })),
    ...s.sinks.map((d) => ({
      id: `T:${d.uid}`,
      column: 2 as const,
      key: d.uid,
      watts: deviceWatts(d),
      hatch: num(d.unexplained),
    })),
  ];
  const links: LinkIn[] = [
    ...s.left.map((l) => ({
      id: l.id,
      source: `S:${l.src}`,
      target: `C:${l.channel}`,
      value: num(l.w),
      side: 'left' as const,
      channel: CHANNELS.indexOf(l.channel),
      src: srcRank.get(l.src)!,
      sink: -1,
    })),
    ...s.right.map((r) => ({
      id: r.id,
      source: `C:${r.channel}`,
      target: `T:${r.sink}`,
      value: num(r.w),
      side: 'right' as const,
      channel: CHANNELS.indexOf(r.channel),
      src: srcRank.get(r.src)!,
      sink: sinkRank.get(r.sink)!,
    })),
  ];

  const columns = [0, 1, 2].map((c) => nodes.filter((n) => n.column === c));
  const totals = columns.map((col) => col.reduce((a, n) => a + n.watts, 0));
  if (Math.max(...totals) <= 0) {
    const {w, h} = g.size(0);
    return {nodes: new Map(), links: new Map(), w, h, empty: true};
  }
  const gapsOf = (c: number) => g.gaps[c] * Math.max(columns[c].length - 1, 0);
  const scale = g.fit
    ? Math.min(
        ...totals.map((t, c) => (t > 0 ? (g.body - gapsOf(c)) / t : Infinity)),
      )
    : g.body / Math.max(...totals);
  const lengthOf = (n: NodeIn) => Math.max(n.watts * scale, n.watts > 0 ? MIN_NODE : 0);
  const colPx = columns.map((col, c) => col.reduce((a, n) => a + lengthOf(n), 0) + gapsOf(c));
  const tallest = g.fit ? g.body : Math.max(...colPx);

  // The graph and the stacking order, from d3-sankey. One comparator orders
  // both ends of every node: links leaving a source by channel, links into a
  // channel by source, links leaving a channel by sink then source, links into
  // a sink by source.
  const generator = sankey<NodeIn, LinkIn>()
    .nodeId((n) => n.id)
    .nodeAlign((n) => (n as N).column)
    .nodeWidth(g.nodeW)
    .nodePadding(g.gaps[0])
    .nodeSort(null as unknown as (a: N, b: N) => number)
    .linkSort((a: L, b: L) => {
      if (a.source === b.source) {
        return a.side === 'left'
          ? a.channel - b.channel
          : a.sink - b.sink || a.src - b.src;
      }
      return a.src - b.src;
    })
    .iterations(0)
    .extent([
      [0, 0],
      [1000, 1000],
    ]);
  const graph: SankeyGraph<NodeIn, LinkIn> = generator({
    nodes: nodes.map((n) => ({...n})),
    links: links.map((l) => ({...l})),
  });

  for (const c of [0, 1, 2]) {
    let b = g.start + (tallest - colPx[c]) / 2;
    for (const n of graph.nodes.filter((x) => x.column === c)) {
      n.x0 = g.cols[c];
      n.x1 = g.cols[c] + g.nodeW;
      n.y0 = b;
      n.y1 = b + lengthOf(n);
      b = n.y1 + g.gaps[c];
    }
  }
  for (const l of graph.links) {
    l.width = l.value * scale;
  }
  generator.update(graph);

  const outNodes = new Map<string, LNode>();
  for (const n of graph.nodes) {
    outNodes.set(n.id, {
      id: n.id,
      column: n.column,
      key: n.key,
      d0: n.x0!,
      d1: n.x1!,
      b0: n.y0!,
      b1: n.y1!,
      hatch: Math.min(n.hatch * scale, n.y1! - n.y0!),
    });
  }
  const outLinks = new Map<string, LLink>();
  for (const l of graph.links) {
    const src = l.source as N;
    const tgt = l.target as N;
    outLinks.set(l.id, {
      id: l.id,
      b0: l.y0!,
      b1: l.y1!,
      d0: src.x1!,
      d1: tgt.x0!,
      width: l.width!,
    });
  }
  const {w, h} = g.size(tallest + g.start);
  return {nodes: outNodes, links: outLinks, w, h, empty: false};
}

/** A ribbon as a filled band, both control points at half the span. */
export function band(l: LLink, vertical: boolean): string {
  const t = Math.max(l.width, 1.5) / 2;
  const dm = (l.d0 + l.d1) / 2;
  const P = (d: number, b: number) => (vertical ? `${b},${d}` : `${d},${b}`);
  return [
    `M${P(l.d0, l.b0 - t)}`,
    `C${P(dm, l.b0 - t)} ${P(dm, l.b1 - t)} ${P(l.d1, l.b1 - t)}`,
    `L${P(l.d1, l.b1 + t)}`,
    `C${P(dm, l.b1 + t)} ${P(dm, l.b0 + t)} ${P(l.d0, l.b0 + t)}`,
    'Z',
  ].join(' ');
}
