import React from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';
import {DeviceGlyph, kindColor} from './icons';
import {fmtShare, fmtW, rat} from './rational';
import {CHANNEL_LABEL, edgeSetLabel, nodeValueLabel, roleText} from './model';
import type {FlowModel, FlowNode} from './model';
import type {LayerId} from './types';

/* Geometry, as designed: two columns, one row per device, edge width ∝ watts. */
const W = 660;
const ROW_H = 116;
const TOP = 66;
const BOTTOM = 52;
const NODE_R = 37;
const COL_X = 96;

interface Point {
  x: number;
  y: number;
}

export interface FlowSvgProps {
  model: FlowModel;
  layer: LayerId;
  selected: FlowNode | null;
  /** Focus a device. */
  onSelect: (uid: string) => void;
  /** Clear the focus — clicking the diagram anywhere but a device. */
  onClear: () => void;
}

export default function FlowSvg({
  model,
  layer,
  selected,
  onSelect,
  onClear,
}: FlowSvgProps): React.ReactElement {
  const left = model.nodes.filter((n) => n.side === 'L');
  const right = model.nodes.filter((n) => n.side === 'R');
  const rows = Math.max(left.length, right.length, 1);
  const height = TOP + rows * ROW_H + BOTTOM - (ROW_H - 74);

  const pos: {[uid: string]: Point} = {};
  const place = (list: FlowNode[], cx: number) => {
    const span = ((rows - list.length) * ROW_H) / 2;
    list.forEach((n, i) => {
      pos[n.uid] = {x: cx, y: TOP + span + i * ROW_H};
    });
  };
  place(left, COL_X);
  place(right, W - COL_X);

  const maxFlow = model.edges.reduce((a, e) => Math.max(a, e.w), 0) || 1;

  // Focus mode: selecting a device fades everything it does not exchange power
  // with, and surfaces the sources it is *allowed* to use but currently isn't.
  let related: {[uid: string]: true} | null = null;
  const potential: string[] = [];
  if (selected) {
    related = {[selected.uid]: true};
    for (const e of model.edges) {
      if (e.from === selected.uid) related[e.to] = true;
      if (e.to === selected.uid) related[e.from] = true;
    }
    const allowed =
      selected.config?.charge_from_adapters ??
      selected.config?.power_from_adapters ??
      [];
    if (selected.role === 'sink' && allowed.length) {
      for (const srcUid of allowed) {
        const used = model.edges.some(
          (e) => e.from === srcUid && e.to === selected.uid,
        );
        if (!used && pos[srcUid]) {
          potential.push(srcUid);
          related[srcUid] = true;
        }
      }
    }
  }

  return (
    // Clicking the diagram anywhere but a device clears the focus. The devices
    // stop the event, so a click on one moves the focus instead of ending it.
    <div className={styles.svgwrap} onClick={onClear}>
      <svg
        className={styles.svg}
        viewBox={`0 0 ${W} ${height}`}
        role="group"
        aria-label="Power flow topology"
      >
        <text
          x={COL_X}
          y={24}
          textAnchor="middle"
          fontSize="10"
          letterSpacing=".08em"
          fill="var(--cd-mut)"
        >
          SOURCES
        </text>
        <text
          x={W - COL_X}
          y={24}
          textAnchor="middle"
          fontSize="10"
          letterSpacing=".08em"
          fill="var(--cd-mut)"
        >
          SINKS
        </text>

        {model.edges.map((e) => {
          const a = pos[e.from];
          const b = pos[e.to];
          if (!a || !b) {
            return null;
          }
          const x1 = a.x + NODE_R + 3;
          const x2 = b.x - NODE_R - 3;
          const mx = (x1 + x2) / 2;
          const kind = model.nodes.find((n) => n.uid === e.from)?.kind ?? 'home';
          const color = kindColor(kind);
          const touches =
            !related || e.from === selected?.uid || e.to === selected?.uid;
          return (
            <path
              key={`${e.from}->${e.to}`}
              className={clsx(styles.edge, styles.flow, !touches && styles.bg)}
              d={`M${x1} ${a.y} C${mx} ${a.y}, ${mx} ${b.y}, ${x2} ${b.y}`}
              style={{color}}
              stroke={color}
              strokeWidth={(1.5 + 8.5 * (e.w / maxFlow)).toFixed(1)}
            >
              <title>{`${e.from} → ${e.to}: ${fmtW(e.w)} (${fmtShare(e.share).dec} of ${e.to})`}</title>
            </path>
          );
        })}

        {selected &&
          potential.map((srcUid) => {
            const a = pos[srcUid];
            const b = pos[selected.uid];
            const sameSide = a.x === b.x;
            const x1 = a.x + NODE_R + 3;
            const x2 = sameSide ? b.x + NODE_R + 3 : b.x - NODE_R - 3;
            const mx = sameSide ? a.x + NODE_R + 60 : (x1 + x2) / 2;
            return (
              <g key={`pot-${srcUid}`}>
                <path
                  className={styles.pot}
                  d={`M${x1} ${a.y} C${mx} ${a.y}, ${mx} ${b.y}, ${x2} ${b.y}`}
                >
                  <title>{`${selected.uid} may use ${srcUid} — currently unused`}</title>
                </path>
                <text
                  className={styles.elabel}
                  x={mx}
                  y={(a.y + b.y) / 2 - 5}
                  textAnchor="middle"
                  opacity=".7"
                >
                  allowed · unused
                </text>
              </g>
            );
          })}

        {model.nodes.map((n) => {
          const p = pos[n.uid];
          if (!p) {
            return null;
          }
          const color = kindColor(n.kind);
          let valueText = nodeValueLabel(model, n, layer);
          let ownText: string | null = null;

          // A related node shows what it exchanges *with the selection*, with
          // its own total demoted to a subtitle.
          if (related && related[n.uid] && selected && n.uid !== selected.uid) {
            const conn = model.edges.filter(
              (e) =>
                (e.from === n.uid && e.to === selected.uid) ||
                (e.from === selected.uid && e.to === n.uid),
            );
            ownText = `of ${valueText}`;
            valueText = edgeSetLabel(model, conn, layer);
          }

          // The channel split is what layer 3 is about, so a sink says which
          // channel it is rather than repeating its uid's watts.
          const caption =
            layer === '3' && n.channel ? CHANNEL_LABEL[n.channel] : null;

          const deficit = model.deficits[n.uid];
          return (
            <g
              key={n.uid}
              className={clsx(
                styles.node,
                n.role === 'idle' && styles.dim,
                selected?.uid === n.uid && styles.sel,
                related && !related[n.uid] && styles.bg,
              )}
              transform={`translate(${p.x} ${p.y})`}
              tabIndex={0}
              role="button"
              aria-pressed={selected?.uid === n.uid}
              aria-label={`${n.uid}, ${roleText(n)}, ${fmtW(Math.abs(n.reading))}`}
              onClick={(ev) => {
                ev.stopPropagation();
                onSelect(n.uid);
              }}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') {
                  ev.preventDefault();
                  ev.stopPropagation();
                  onSelect(n.uid);
                }
              }}
            >
              <circle
                className={styles.ring}
                r={NODE_R}
                fill="var(--cd-bg)"
                stroke={color}
                strokeWidth="2.5"
                strokeDasharray={n.virtual ? '5 4' : undefined}
              />
              <g transform="translate(0 -9)">
                <DeviceGlyph kind={n.kind} />
              </g>
              <text
                y={ownText ? 17 : 20}
                textAnchor="middle"
                fontSize="12"
                fontWeight="600"
                fill="var(--cd-fg)"
                fontFamily="inherit"
              >
                {valueText}
              </text>
              {ownText && (
                <text
                  y={29}
                  textAnchor="middle"
                  fontSize="9"
                  fill="var(--cd-mut)"
                  fontFamily="inherit"
                >
                  {ownText}
                </text>
              )}
              <text
                y={NODE_R + 17}
                textAnchor="middle"
                fontSize="11.5"
                fontFamily="ui-monospace, Menlo, monospace"
                fill="var(--cd-mut)"
              >
                {n.uid}
              </text>
              {caption && (
                <text
                  y={NODE_R + 30}
                  textAnchor="middle"
                  fontSize="9.5"
                  letterSpacing=".05em"
                  fill="var(--cd-mut)"
                  fontFamily="inherit"
                  opacity="0.8"
                >
                  {caption}
                </text>
              )}
              {deficit && (
                <g transform={`translate(${NODE_R - 10} ${-NODE_R + 10})`}>
                  <circle r="8.5" fill="var(--cd-amber)" />
                  <text
                    y="3.5"
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="700"
                    fill="#fff"
                  >
                    !
                  </text>
                  <title>{`Restriction deficit: ${fmtW(rat(deficit))}`}</title>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
