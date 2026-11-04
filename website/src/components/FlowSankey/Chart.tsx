import React from 'react';
import clsx from 'clsx';

import styles from './styles.module.css';
import {fmtW} from './fraction';
import {linkLabel, nodeLabel, type Focus, type Norm} from './focus';
import {band, type Layout, type LNode} from './layout';
import {deviceOf, type Basis, type Snapshot} from './model';

export interface ChartProps {
  s: Snapshot;
  lay: Layout;
  vertical: boolean;
  norm: Norm;
  basis: Basis;
  path: Set<string> | null;
  pinned: Focus;
  /** Unique, SVG-safe prefix for this chart's gradient and pattern ids. */
  idp: string;
  onHover: (f: Focus, at: {x: number; y: number} | Element | null) => void;
  onPin: (f: Focus) => void;
}

/** Ribbon end labels appear only on ribbons at least this thick. */
const LABEL_MIN = 9;

/**
 * Push label centres apart so neighbours do not overlap, keeping their order:
 * small bars sit close together, and their labels need more room than they do.
 */
function spread(items: {c: number; size: number}[], lo = -Infinity, hi = Infinity): number[] {
  const out = items.map((x) => x.c);
  for (let i = 0; i < out.length; i++) {
    const min = i === 0 ? lo + items[0].size / 2 : out[i - 1] + (items[i - 1].size + items[i].size) / 2;
    out[i] = Math.max(out[i], min);
  }
  // Then back from the far edge, so nothing is pushed off the canvas.
  for (let i = out.length - 1; i >= 0; i--) {
    const max =
      i === out.length - 1 ? hi - items[i].size / 2 : out[i + 1] - (items[i + 1].size + items[i].size) / 2;
    out[i] = Math.min(out[i], max);
  }
  return out;
}

/** A rough text width, enough to keep narrow-layout labels apart. */
const textW = (s: string, px: number) => s.length * px * 0.56;

export default function Chart({
  s,
  lay,
  vertical,
  norm,
  basis,
  path,
  pinned,
  idp,
  onHover,
  onPin,
}: ChartProps): React.ReactElement {
  const P = (d: number, b: number) => (vertical ? {x: b, y: d} : {x: d, y: b});
  const nodes = [...lay.nodes.values()];
  const sources = nodes.filter((n) => n.column === 0);
  const channels = nodes.filter((n) => n.column === 1);
  const sinks = nodes.filter((n) => n.column === 2);
  const lit = (id: string) => !path || path.has(id);

  const interact = (f: NonNullable<Focus>) => ({
    tabIndex: 0,
    role: 'button',
    'aria-pressed': pinned?.id === f.id,
    onPointerEnter: (e: React.PointerEvent) => onHover(f, {x: e.clientX, y: e.clientY}),
    onPointerMove: (e: React.PointerEvent) => onHover(f, {x: e.clientX, y: e.clientY}),
    onPointerLeave: () => onHover(null, null),
    onFocus: (e: React.FocusEvent) => onHover(f, e.currentTarget),
    onBlur: () => onHover(null, null),
    onClick: () => onPin(pinned?.id === f.id ? null : f),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onPin(pinned?.id === f.id ? null : f);
      }
    },
  });

  // Device labels: value and caption, kept apart within their column.
  const deviceLabels = (col: LNode[], side: 'before' | 'after') => {
    // The narrow chart has no room for the role: the device name alone.
    const texts = col.map((n) => {
      const t = nodeLabel(s, n.id, norm, basis);
      return vertical ? {...t, caption: n.key} : t;
    });
    const extrasOf = (key: string) => {
      const d = deviceOf(s, key);
      const out: {text: string; cls: string}[] = [];
      if (d.unexplained.n > 0n) {
        out.push({text: `${fmtW(d.unexplained)} unexplained`, cls: styles.ncapMuted});
      }
      if (s.broken.some((x) => x.sink === d.uid)) {
        out.push({text: vertical ? '▲ relaxed' : '▲ restriction relaxed', cls: styles.nwarn});
      }
      return out;
    };
    const sizes = texts.map((t, i) =>
      vertical
        ? Math.max(textW(t.value, 15), textW(t.caption, 10), ...extrasOf(col[i].key).map((e) => textW(e.text, 10))) + 10
        : 38,
    );
    const centres = vertical
      ? spread(col.map((n, i) => ({c: (n.b0 + n.b1) / 2, size: sizes[i]})), 2, lay.w - 2)
      : spread(col.map((n, i) => ({c: (n.b0 + n.b1) / 2, size: sizes[i]})));
    return col.map((n, i) => {
      const d = deviceOf(s, n.key);
      const t = texts[i];
      const c = centres[i];
      const extra = extrasOf(n.key);
      if (vertical) {
        const above = side === 'before';
        const y0 = above ? n.d0 - 26 - extra.length * 12 : n.d1 + 20;
        return (
          <g key={`l${n.id}`} className={clsx(!lit(n.id) && styles.dimText)} aria-hidden="true">
            <text x={c} y={y0} textAnchor="middle" className={styles.nvalueSm}>
              {t.value}
            </text>
            <text x={c} y={y0 + 13} textAnchor="middle" className={styles.ncap}>
              {t.caption}
            </text>
            {extra.map((e, j) => (
              <text key={j} x={c} y={y0 + 25 + j * 12} textAnchor="middle" className={e.cls}>
                {e.text}
              </text>
            ))}
          </g>
        );
      }
      const x = side === 'before' ? n.d0 - 12 : n.d1 + 12;
      const anchor = side === 'before' ? 'end' : 'start';
      return (
        <g key={`l${n.id}`} className={clsx(!lit(n.id) && styles.dimText)} aria-hidden="true">
          <text x={x} y={c + 2} textAnchor={anchor} className={styles.nvalue}>
            {t.value}
          </text>
          <text x={x} y={c + 18} textAnchor={anchor} className={styles.ncap}>
            {t.caption}
          </text>
          {extra.map((e, j) => (
            <text key={j} x={x} y={c + 31 + j * 12} textAnchor={anchor} className={e.cls}>
              {e.text}
            </text>
          ))}
        </g>
      );
    });
  };

  // Narrow: channel titles sit side by side on one row, so keep them apart.
  const channelMids = spread(
    channels.map((n) => ({
      c: (n.b0 + n.b1) / 2,
      size: textW(nodeLabel(s, n.id, norm, basis).value, 12) + 10,
    })),
    2,
    lay.w - 2,
  );

  const sourceColors = new Map(s.sources.map((d) => [d.uid, d.color]));
  const heads: [number, string][] = [
    [0, 'SOURCES'],
    [1, 'CHANNELS'],
    [2, 'SINKS'],
  ];
  const geomCols = [sources, channels, sinks].map((col, i) =>
    col[0] ? (col[0].d0 + col[0].d1) / 2 : null,
  );

  return (
    <svg
      viewBox={`0 0 ${lay.w} ${lay.h}`}
      className={clsx(styles.svg, vertical ? styles.svgNarrow : styles.svgWide)}
      role="group"
      aria-label={`Power flow, ${s.caseTitle} snapshot ${s.index + 1}`}
    >
      <defs>
        {s.sources.map((d) => (
          <linearGradient
            key={d.uid}
            id={`${idp}g-${d.uid}`}
            x1="0"
            y1="0"
            x2={vertical ? '0' : '1'}
            y2={vertical ? '1' : '0'}
          >
            <stop offset="0" style={{stopColor: d.color}} stopOpacity="0.62" />
            <stop offset="1" style={{stopColor: d.color}} stopOpacity="0.3" />
          </linearGradient>
        ))}
        <pattern
          id={`${idp}hatch`}
          width="5"
          height="5"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width="5" height="5" className={styles.hatchBg} />
          <line x1="0" y1="0" x2="0" y2="5" className={styles.hatchLine} />
        </pattern>
      </defs>

      {!vertical &&
        heads.map(([c, label]) =>
          geomCols[c] === null ? null : (
            <text key={label} x={geomCols[c]!} y={22} textAnchor="middle" className={styles.colhead}>
              {label}
            </text>
          ),
        )}

      <g>
        {s.left.map((l) => {
          const g = lay.links.get(l.id);
          return g ? (
            <path
              key={l.id}
              d={band(g, vertical)}
              className={clsx(styles.ribbon, styles.ribbonLeft, !lit(l.id) && styles.dim)}
              style={{fill: sourceColors.get(l.src)}}
              aria-label={`${l.src} to ${l.channel}: ${linkLabel(s, l.id, 'watts', basis)}`}
              {...interact({type: 'link', id: l.id})}
            />
          ) : null;
        })}
        {s.right.map((r) => {
          const g = lay.links.get(r.id);
          return g ? (
            <path
              key={r.id}
              d={band(g, vertical)}
              className={clsx(styles.ribbon, !lit(r.id) && styles.dim)}
              style={{fill: `url(#${idp}g-${r.src})`}}
              aria-label={`${r.src} to ${r.sink}: ${linkLabel(s, r.id, 'watts', basis)}`}
              {...interact({type: 'link', id: r.id})}
            />
          ) : null;
        })}
      </g>

      <g aria-hidden="true">
        {[...s.left, ...s.right].map((x) => {
          const g = lay.links.get(x.id);
          if (!g || !lit(x.id)) {
            return null;
          }
          const label = linkLabel(s, x.id, norm, basis);
          const isLeft = x.id.startsWith('L');
          // Across the flow the narrow layout needs room for the whole label.
          const room = vertical ? textW(label ?? '', 10) + 6 : LABEL_MIN;
          if (!label || g.width < room) {
            return null;
          }
          const at = isLeft
            ? P(g.d0 + (vertical ? 13 : 8), g.b0)
            : P(g.d1 - (vertical ? 6 : 8), g.b1);
          return (
            <text
              key={`t${x.id}`}
              x={at.x}
              y={at.y + (vertical ? 0 : 3.5)}
              textAnchor={vertical ? 'middle' : isLeft ? 'start' : 'end'}
              className={styles.rlabel}
            >
              {label}
            </text>
          );
        })}
      </g>

      {nodes.map((n) => {
        const isChannel = n.column === 1;
        const d = isChannel ? null : deviceOf(s, n.key);
        const a = P(n.d0, n.b0);
        const w = vertical ? n.b1 - n.b0 : n.d1 - n.d0;
        const h = vertical ? n.d1 - n.d0 : n.b1 - n.b0;
        const hatch =
          n.hatch > 0
            ? vertical
              ? {x: n.b1 - n.hatch, y: n.d0, width: n.hatch, height: h}
              : {x: n.d0, y: n.b1 - n.hatch, width: w, height: n.hatch}
            : null;
        const label = nodeLabel(s, n.id, norm, basis);
        return (
          <g
            key={n.id}
            className={clsx(styles.node, !lit(n.id) && styles.dimNode, pinned?.id === n.id && styles.pinned)}
            aria-label={`${label.value}, ${label.caption}`}
            {...interact({type: 'node', id: n.id})}
          >
            <rect
              x={a.x}
              y={a.y}
              width={w}
              height={h}
              rx={3}
              className={clsx(
                styles.bar,
                isChannel && styles.barChannel,
                d?.kind === 'home' && styles.barHome,
                !s.provenance && styles.barMuted,
              )}
              style={isChannel || !s.provenance ? undefined : {fill: d!.color, stroke: d!.kind === 'home' ? d!.color : undefined}}
            />
            {hatch && <rect {...hatch} fill={`url(#${idp}hatch)`} className={styles.hatch} />}
            {/* A wider invisible target than the 8 px bar. */}
            <rect
              x={vertical ? a.x : a.x - 6}
              y={vertical ? a.y - 6 : a.y}
              width={vertical ? w : w + 12}
              height={vertical ? h + 12 : h}
              fill="transparent"
            />
          </g>
        );
      })}

      <g aria-hidden="true">
        {channels.map((n, i) => {
          const t = nodeLabel(s, n.id, norm, basis);
          if (vertical) {
            const sub = t.caption.split(' · ')[0];
            const mid = channelMids[i];
            return (
              <g key={`l${n.id}`} className={clsx(!lit(n.id) && styles.dimText)}>
                <text x={mid} y={n.d0 - 7} textAnchor="middle" className={styles.chTitleSm}>
                  {t.value}
                </text>
                <text x={mid} y={n.d1 + 13} textAnchor="middle" className={styles.chSub}>
                  {sub}
                </text>
              </g>
            );
          }
          return (
            <g key={`l${n.id}`} className={clsx(!lit(n.id) && styles.dimText)}>
              <text x={n.d0 + 4} y={n.b0 - 22} textAnchor="middle" className={styles.chTitle}>
                {t.value}
              </text>
              <text x={n.d0 + 4} y={n.b0 - 8} textAnchor="middle" className={styles.chSub}>
                {t.caption}
              </text>
            </g>
          );
        })}
        {deviceLabels(sources, 'before')}
        {deviceLabels(sinks, 'after')}
      </g>
    </svg>
  );
}
