import React, {useEffect, useMemo, useState} from 'react';
import clsx from 'clsx';

import styles from './styles.module.css';
import {fmtUnit, fmtW, humanize, rat} from '../CaseDiagram/rational';
import {DeviceIcon, KIND_LABEL, kindColor} from '../CaseDiagram/icons';
import type {PropertyCatalog, ReferenceCase} from '../CaseDiagram/types';
import {
  COL_X,
  NODE_W,
  WIDTH,
  buildSankey,
  lookup,
  ribbonPath,
  type SankeyModel,
  type SLink,
  type SNode,
} from './layout';
import {
  CHANNEL_MONEY,
  CHANNEL_SENSORS,
  CHANNEL_TITLE,
  CHANNELS,
  headlineMoney,
  linkSensors,
  sinkMoneySensors,
  sourceMoneySensors,
  type Channel,
  type SensorRef,
} from './sensors';

/**
 * PROTOTYPE — a Sankey take on the reference-case diagram.
 *
 * Three columns instead of two: sources → the four channels of gross power →
 * sinks. That puts the per-source channel sensors (the bulk of what a grid, PV
 * or battery device exposes in Home Assistant) on the picture as links, and
 * the provenance matrix on it as source-coloured ribbons into each sink.
 *
 * Ribbon widths are always watts. The view switch only changes what the labels
 * say, and in the money view every figure is an engine value, never a
 * browser-side watts × price.
 */

type View = 'watts' | 'shares' | 'money';

const VIEWS: {id: View; label: string}[] = [
  {id: 'watts', label: 'Watts'},
  {id: 'shares', label: 'Shares & ratios'},
  {id: 'money', label: 'Money'},
];

type Selection = {type: 'node'; id: string} | {type: 'link'; id: string} | null;

interface Props {
  case: ReferenceCase;
  properties: PropertyCatalog;
}

export default function FlowSankey({case: refCase, properties}: Props) {
  const [stateId, setStateId] = useState(refCase.states[0]?.id ?? '');
  const [view, setView] = useState<View>('watts');
  const [selected, setSelected] = useState<Selection>(null);
  const [hover, setHover] = useState<Selection>(null);

  // Deep link, read after mount so server and first client render agree.
  useEffect(() => {
    const want = new URLSearchParams(window.location.search).get('state');
    if (want && refCase.states.some((s) => s.id === want)) {
      setStateId(want);
    }
  }, [refCase]);

  const state = refCase.states.find((s) => s.id === stateId) ?? refCase.states[0];
  const model = useMemo(() => buildSankey(refCase, state), [refCase, state]);

  const focus = hover ?? selected;
  const active = useMemo(() => activeSet(model, focus), [model, focus]);

  const val = (ref: SensorRef) => lookup(model.byProperty, ref.property, ref.key);
  const fmt = (ref: SensorRef) => {
    const stored = val(ref);
    if (stored === null || stored === undefined) {
      return {text: '—', frac: null};
    }
    return fmtUnit(stored, properties.properties[ref.property]?.unit);
  };

  const gross = lookup(model.byProperty, 'gross_power');
  const imbalance = lookup(model.byProperty, 'metering_imbalance');

  return (
    <div className={styles.root}>
      <div className={styles.states} role="tablist" aria-label="Snapshot">
        {refCase.states.map((s, i) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={s.id === state.id}
            className={clsx(styles.state, s.id === state.id && styles.on)}
            onClick={() => {
              setStateId(s.id);
              setSelected(null);
            }}>
            <span className={styles.stnum}>{String(i + 1).padStart(2, '0')}</span>
            <span className={styles.sttitle}>{humanize(s.id)}</span>
            <span className={styles.stnote}>{s.note}</span>
          </button>
        ))}
      </div>

      <div className={styles.bar}>
        <div className={styles.kpis}>
          <span>
            Available power <b>{fmtW(gross == null ? null : rat(gross))}</b>
          </span>
          <span>
            Grid price <b>{state.price === null ? '—' : fmtUnit(state.price, 'EUR/kWh').text}</b>
          </span>
          <span className={clsx(imbalance && rat(imbalance) !== 0 && styles.warn)}>
            Metering imbalance <b>{fmtW(imbalance == null ? null : rat(imbalance))}</b>
          </span>
        </div>
        <div className={styles.views} role="tablist" aria-label="Labels">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              role="tab"
              aria-selected={view === v.id}
              className={clsx(styles.view, view === v.id && styles.on)}
              onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.svgwrap}>
        <svg
          viewBox={`0 0 ${WIDTH} ${model.height}`}
          className={styles.svg}
          role="img"
          aria-label={`Power flow for ${humanize(state.id)}`}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}>
          <text x={COL_X[0] + NODE_W} y={14} className={styles.colhead} textAnchor="end">
            SOURCES
          </text>
          <text x={COL_X[1] + NODE_W / 2} y={14} className={styles.colhead} textAnchor="middle">
            CHANNELS
          </text>
          <text x={COL_X[2]} y={14} className={styles.colhead}>
            SINKS
          </text>

          <g>
            {model.links.map((l) => (
              <path
                key={l.id + l.segment}
                d={ribbonPath(l)}
                className={clsx(
                  styles.ribbon,
                  active && !active.has(linkKey(l)) && styles.dim,
                  active?.has(linkKey(l)) && styles.lit,
                )}
                style={{fill: l.color}}
                onMouseEnter={() => setHover({type: 'link', id: linkKey(l)})}
                onMouseLeave={() => setHover(null)}
                onClick={() => setSelected({type: 'link', id: linkKey(l)})}>
                <title>{linkTitle(l)}</title>
              </path>
            ))}
          </g>

          <g>
            {model.links
              .filter((l) => l.thickness >= 13)
              .map((l) => {
                const text = ribbonLabel(l, view, model);
                if (!text) return null;
                const left = l.segment === 'left';
                return (
                  <text
                    key={`t${l.id}${l.segment}`}
                    x={left ? COL_X[0] + NODE_W + 8 : COL_X[2] - 8}
                    y={(left ? l.y0 : l.y1) + 4}
                    textAnchor={left ? 'start' : 'end'}
                    className={clsx(
                      styles.rlabel,
                      active && !active.has(linkKey(l)) && styles.dimtext,
                    )}>
                    {text}
                  </text>
                );
              })}
          </g>

          {model.nodes.map((n) => (
            <NodeMark
              key={n.id}
              n={n}
              view={view}
              model={model}
              dim={!!active && !active.has(n.id)}
              selected={selected?.type === 'node' && selected.id === n.id}
              money={(ref) => fmt(ref).text}
              onHover={(on) => setHover(on ? {type: 'node', id: n.id} : null)}
              onSelect={() => setSelected({type: 'node', id: n.id})}
              deficit={lookup(model.byProperty, 'sink_adapters_restriction_deficit', n.id)}
            />
          ))}
        </svg>
      </div>

      {model.idle.length > 0 && (
        <div className={styles.idle}>
          Idle this snapshot:{' '}
          {model.idle.map((d) => (
            <span key={d.uid}>
              <span className={styles.dot} style={{background: kindColor(d.kind)}} />
              {d.uid}{' '}
              <i>{state.readings[d.uid] === null ? 'unavailable' : '0 W'}</i>
            </span>
          ))}
        </div>
      )}

      <Detail
        selection={selected}
        model={model}
        refCase={refCase}
        stateReadings={state.readings}
        fmt={fmt}
        onClear={() => setSelected(null)}
      />
    </div>
  );
}

function linkKey(l: SLink): string {
  return `${l.segment}:${l.id}`;
}

/** Everything that should stay lit while `focus` is highlighted. */
function activeSet(m: SankeyModel, focus: Selection): Set<string> | null {
  if (!focus) return null;
  const on = new Set<string>();
  if (focus.type === 'link') {
    const l = m.links.find((x) => linkKey(x) === focus.id);
    if (!l) return null;
    on.add(focus.id).add(l.from).add(l.to);
    // A ribbon into a sink is lit together with its source's link into the channel.
    for (const x of m.links) {
      if (x.source === l.source && x.channel === l.channel) {
        on.add(linkKey(x)).add(x.from).add(x.to);
      }
    }
    on.add(l.source);
    return on;
  }
  on.add(focus.id);
  for (const x of m.links) {
    const touches =
      x.from === focus.id || x.to === focus.id || x.source === focus.id;
    // A sink lights the source links feeding its channel from its own sources.
    const feedsSink = m.links.some(
      (r) => r.to === focus.id && r.source === x.source && r.channel === x.channel,
    );
    if (touches || feedsSink) {
      on.add(linkKey(x)).add(x.from).add(x.to);
    }
  }
  return on;
}

function linkTitle(l: SLink): string {
  const src = l.source;
  if (l.segment === 'left') {
    return `${src} → ${CHANNEL_TITLE[l.channel]}: ${fmtW(l.w)} (source_adapters_${l.channel}_power = ${l.stored})`;
  }
  return `${src} → ${l.to}: ${fmtW(l.w)} (${l.stored} of ${l.to}'s draw, from the provenance matrix)`;
}

function ribbonLabel(l: SLink, view: View, m: SankeyModel): string | null {
  if (view === 'money') return null;
  if (view === 'watts') return fmtW(l.w);
  if (l.segment === 'left') {
    const ratio = lookup(m.byProperty, `source_adapters_${l.channel}_ratios`, l.source);
    return ratio == null ? null : `${fmtUnit(ratio, 'ratio').text} of ${l.source}`;
  }
  return `${fmtUnit(l.stored, 'share').text} of ${l.to}`;
}

function NodeMark({
  n,
  view,
  model,
  dim,
  selected,
  money,
  onHover,
  onSelect,
  deficit,
}: {
  n: SNode;
  view: View;
  model: SankeyModel;
  dim: boolean;
  selected: boolean;
  money: (ref: SensorRef) => string;
  onHover: (on: boolean) => void;
  onSelect: () => void;
  deficit: string | null | undefined;
}) {
  const isChannel = n.kind === 'channel';
  const cy = n.y + n.h / 2;

  let value: string;
  if (isChannel) {
    const ch = n.channel as Channel;
    value =
      view === 'money'
        ? money(CHANNEL_MONEY[ch])
        : view === 'shares'
          ? `${fmtUnit(lookup(model.byProperty, `gross_power_${ch}_ratio`) ?? '0', 'ratio').text} of gross`
          : fmtW(n.w);
  } else if (view === 'money') {
    value = money(headlineMoney(n.column === 0 ? 'source' : 'sink', n.kind as never, n.id));
  } else {
    value = fmtW(n.w);
  }

  const label = isChannel ? CHANNEL_TITLE[n.channel as Channel] : n.id;
  const sub = isChannel
    ? null
    : n.id === 'home'
      ? 'unmetered base load'
      : KIND_LABEL[n.kind as never];

  const keyActivate = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect();
    }
  };

  return (
    <g
      className={clsx(styles.node, dim && styles.dimnode, selected && styles.sel)}
      tabIndex={0}
      role="button"
      aria-label={`${label}: ${value}`}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onFocus={() => onHover(true)}
      onBlur={() => onHover(false)}
      onClick={onSelect}
      onKeyDown={keyActivate}>
      <rect
        x={n.x}
        y={n.y}
        width={NODE_W}
        height={n.h}
        rx={2}
        style={{fill: n.color}}
        className={clsx(styles.nbar, n.id === 'home' && styles.virtual)}
      />
      {isChannel ? (
        <>
          <text x={n.x + NODE_W / 2} y={n.y - 18} textAnchor="middle" className={styles.nlabel}>
            {label}
          </text>
          <text x={n.x + NODE_W / 2} y={n.y - 5} textAnchor="middle" className={styles.nvalue}>
            {value}
          </text>
        </>
      ) : (
        <>
          {/* Makes the label and icon clickable, not just the thin bar. */}
          <rect
            x={n.column === 0 ? n.x - 180 : n.x + NODE_W}
            y={Math.min(n.y, cy - 17)}
            width={180}
            height={Math.max(n.h, 34)}
            fill="transparent"
          />
          <g
            transform={`translate(${n.column === 0 ? n.x - 20 : n.x + NODE_W + 20} ${cy}) scale(0.8)`}>
            <DeviceIcon kind={n.kind as never} />
          </g>
          <text
            x={n.column === 0 ? n.x - 38 : n.x + NODE_W + 38}
            y={cy - 3}
            textAnchor={n.column === 0 ? 'end' : 'start'}
            className={styles.nlabel}>
            {label} <tspan className={styles.nvalue}>{value}</tspan>
          </text>
          <text
            x={n.column === 0 ? n.x - 38 : n.x + NODE_W + 38}
            y={cy + 11}
            textAnchor={n.column === 0 ? 'end' : 'start'}
            className={styles.nsub}>
            {sub}
          </text>
          {deficit && rat(deficit) > 0 && (
            <text x={n.x + NODE_W + 38} y={cy + 24} className={styles.deficit}>
              ⚠ restriction deficit {fmtW(rat(deficit))}
            </text>
          )}
        </>
      )}
    </g>
  );
}

function Detail({
  selection,
  model,
  refCase,
  stateReadings,
  fmt,
  onClear,
}: {
  selection: Selection;
  model: SankeyModel;
  refCase: ReferenceCase;
  stateReadings: {[uid: string]: string | null};
  fmt: (ref: SensorRef) => {text: string; frac: string | null};
  onClear: () => void;
}) {
  if (!selection) {
    return (
      <div className={styles.detail}>
        <p className={styles.hint}>
          Select a device, a channel or a ribbon to see which Home Assistant sensors
          show it. Ribbon widths are watts in every view; the view switch only
          changes the labels.
        </p>
      </div>
    );
  }

  const kindOf = (uid: string) =>
    uid === 'home' ? 'home' : refCase.topology.find((d) => d.uid === uid)?.kind;

  const rows: {group: string; refs: (SensorRef | {derived: string; label: string})[]}[] = [];
  let title = '';
  let subtitle = '';

  if (selection.type === 'link') {
    const l = model.links.find((x) => linkKey(x) === selection.id)!;
    if (l.segment === 'left') {
      title = `${l.source} → ${CHANNEL_TITLE[l.channel]}`;
      subtitle = 'One link = three sensors on the source device';
      const s = linkSensors(kindOf(l.source) as never, l.source, l.channel);
      if (s) rows.push({group: `Sensors on ${l.source}`, refs: [s.power, s.ratio, s.share]});
    } else {
      title = `${l.source} → ${l.to} (via ${CHANNEL_TITLE[l.channel].toLowerCase()})`;
      subtitle = 'Provenance: not a sensor, derived from the share matrix';
      const draw =
        l.to === 'home'
          ? rat(lookup(model.byProperty, 'home_base_load_power'))
          : Math.abs(rat(stateReadings[l.to]));
      const matrixCell =
        l.to === 'home'
          ? `home_base_load_source_shares[${l.source}]`
          : `sink_adapters_source_shares[${l.to}][${l.source}]`;
      rows.push({
        group: 'Engine values',
        refs: [
          {derived: `${fmtUnit(l.stored, 'share').text} = ${l.stored}`, label: matrixCell},
          {derived: fmtW(l.w), label: `watts = share × ${l.to}'s ${fmtW(draw)}`},
        ],
      });
    }
  } else {
    const n = model.nodes.find((x) => x.id === selection.id)!;
    if (n.kind === 'channel') {
      const ch = n.channel as Channel;
      title = CHANNEL_TITLE[ch];
      subtitle = 'Channel of gross power: whole-home sensors';
      rows.push({group: 'Integration-level sensors', refs: CHANNEL_SENSORS[ch]});
      const shareRefs = model.links
        .filter((l) => l.segment === 'left' && l.channel === ch)
        .map((l) => linkSensors(kindOf(l.source) as never, l.source, ch)?.share)
        .filter(Boolean) as SensorRef[];
      rows.push({group: 'Who supplies it (per-source share sensors)', refs: shareRefs});
    } else if (n.column === 0) {
      const kind = kindOf(n.id) as never;
      title = n.id;
      subtitle = `${KIND_LABEL[kind]} · source · reading ${fmtW(rat(stateReadings[n.id]))}`;
      for (const ch of CHANNELS) {
        const s = linkSensors(kind, n.id, ch);
        if (s) rows.push({group: CHANNEL_TITLE[ch], refs: [s.power, s.ratio, s.share]});
      }
      rows.push({group: 'Money', refs: sourceMoneySensors(kind, n.id)});
    } else {
      const kind = kindOf(n.id) as never;
      title = n.id;
      subtitle =
        n.id === 'home'
          ? 'Unmetered base load · sink'
          : `${KIND_LABEL[kind]} · sink · reading ${fmtW(rat(stateReadings[n.id]))}`;
      const prov = model.links
        .filter((l) => l.segment === 'right' && l.to === n.id)
        .map((l) => ({
          derived: `${fmtW(l.w)} · ${fmtUnit(l.stored, 'share').text} = ${l.stored}`,
          label: `from ${l.source}`,
        }));
      rows.push({group: 'Provenance (share matrix, not sensors)', refs: prov});
      const deficit = lookup(model.byProperty, 'sink_adapters_restriction_deficit', n.id);
      if (deficit && rat(deficit) > 0) {
        rows.push({
          group: 'Restriction',
          refs: [{derived: fmtW(rat(deficit)), label: 'sink_adapters_restriction_deficit'}],
        });
      }
      rows.push({group: 'Sensors', refs: sinkMoneySensors(kind, n.id)});
    }
  }

  return (
    <div className={styles.detail}>
      <div className={styles.dhead}>
        <div>
          <b>{title}</b>
          <span>{subtitle}</span>
        </div>
        <button onClick={onClear} aria-label="Clear selection">
          ×
        </button>
      </div>
      {rows.map((r) => (
        <table key={r.group} className={styles.table}>
          <caption>{r.group}</caption>
          <tbody>
            {r.refs.map((ref, i) =>
              'derived' in ref ? (
                <tr key={i} className={styles.derived}>
                  <td>{ref.label}</td>
                  <td />
                  <td>{ref.derived}</td>
                </tr>
              ) : (
                <tr key={i}>
                  <td>{ref.sensor}</td>
                  <td className={styles.prop}>
                    {ref.property}
                    {ref.key ? `[${ref.key}]` : ''}
                  </td>
                  <td>
                    {fmt(ref).text}
                    {fmt(ref).frac && <span className={styles.frac}> = {fmt(ref).frac}</span>}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      ))}
    </div>
  );
}
