import React, {useState} from 'react';
import clsx from 'clsx';

import styles from './styles.module.css';
import {
  abs,
  div,
  exact,
  fmtEur,
  fmtEurKwh,
  fmtPct,
  fmtW,
  frac,
  fracText,
  isZero,
  num,
  type Frac,
} from './fraction';
import {pctExact, type Focus, type Norm} from './focus';
import {
  CHANNEL_TITLE,
  allowed,
  rightMoney,
  value,
  type Basis,
  type Device,
  type Snapshot,
} from './model';
import type {Channel, PropertyDoc, ValueTree} from './types';

type Section = 1 | 2 | 3 | 4;

const SECTIONS: {id: Section; label: string}[] = [
  {id: 1, label: '1 · Readings and totals'},
  {id: 2, label: '2 · Source × sink'},
  {id: 3, label: '3 · Per-source channels'},
  {id: 4, label: '4 · Every engine value'},
];

interface Props {
  s: Snapshot;
  norm: Norm;
  basis: Basis;
  focus: Focus;
  onFocus: (f: Focus) => void;
}

export default function DataTable(props: Props): React.ReactElement {
  const [section, setSection] = useState<Section>(1);
  return (
    <div className={styles.tables}>
      <div className={styles.tabs} role="tablist" aria-label="Data table">
        {SECTIONS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={section === t.id}
            className={clsx(styles.tab, section === t.id && styles.on)}
            onClick={() => setSection(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className={styles.tableScroll} role="tabpanel">
        {section === 1 && <Readings {...props} />}
        {section === 2 && <Matrix {...props} />}
        {section === 3 && <PerSource {...props} />}
        {section === 4 && <Everything {...props} />}
      </div>
    </div>
  );
}

const list = (items: [string, Frac | null][]) =>
  items.map(([k, v]) => `${k} ${fmtW(v)}`).join(' · ');

/** 1 · Readings and totals — the engine's layer-1 properties, catalog order. */
function Readings({s}: Props) {
  const rows = Object.entries(s.catalog.properties).filter(([, doc]) => doc.layer === 1);
  const madeOf = (p: string, v: Frac | null): string => {
    const of = (pred: (d: Device) => boolean) =>
      s.devices.filter((d) => d.uid !== 'home' && pred(d)).map((d) => [d.uid, d.reading && abs(d.reading)] as [string, Frac | null]);
    switch (p) {
      case 'gross_power':
        return s.sources.length ? list(of((d) => d.role === 'source')) : 'no source delivers anything';
      case 'combined_grid_import':
        return isZero(v) ? 'nothing drawn from the grid' : list(of((d) => d.kind === 'grid'));
      case 'combined_grid_export': {
        const parts = s.left.filter((l) => l.channel === 'export');
        return parts.length ? list(parts.map((l) => [l.src, l.w])) : 'nothing exported';
      }
      case 'combined_production': {
        const pv = of((d) => d.kind === 'pv' && d.role !== 'sink');
        return pv.length ? list(pv) : 'no PV system';
      }
      case 'combined_charging_power':
        return isZero(v) ? 'no battery charging' : list(of((d) => d.kind === 'battery' && d.role === 'sink'));
      case 'combined_discharging_power':
        return isZero(v) ? 'no battery discharging' : list(of((d) => d.kind === 'battery' && d.role === 'source'));
      case 'combined_standby_power':
        return isZero(v) ? 'no standby draw' : list(of((d) => d.kind === 'pv' && d.role === 'sink'));
      case 'combined_consumption': {
        const parts = s.left.filter((l) => l.channel === 'consumption');
        return parts.length ? list(parts.map((l) => [l.src, l.w])) : 'nothing consumed';
      }
      case 'metering_imbalance':
        return isZero(v)
          ? 'readings reconcile exactly'
          : 'metered sinks drew more than the sources supplied; the engine balances the readings';
      case 'home_base_load_power':
        return 'unmetered remainder of consumption';
      default:
        return '';
    }
  };
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Reading</th>
          <th className={styles.num}>W</th>
          <th className={styles.num}>Of gross</th>
          <th className={styles.barCol}>Share</th>
          <th>Made of</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([p, doc]) => {
          const v = value(s, p);
          const published = s.values.get(p) != null;
          const zero = published && isZero(v);
          const ofGross = v && s.gross && !isZero(s.gross) ? div(v, s.gross) : null;
          return (
            <tr key={p} className={clsx(zero && styles.zero)}>
              <td>
                {doc.title}
                {p === 'metering_imbalance' && published && (
                  <span className={clsx(styles.pill, zero ? styles.pillOk : styles.pillWarn)}>
                    {zero ? 'ok' : 'unexplained'}
                  </span>
                )}
              </td>
              <td className={clsx(styles.num, published ? styles.strong : styles.zeroVal)}>
                {published ? fmtW(v) : 'unavailable'}
              </td>
              <td className={clsx(styles.num, styles.mono)}>{ofGross ? fracText(ofGross) : '—'}</td>
              <td className={styles.barCol}>
                <span className={styles.track}>
                  <span className={styles.fill} style={{width: `${Math.min(num(ofGross), 1) * 100}%`}} />
                </span>
              </td>
              <td className={styles.muted}>{published ? madeOf(p, v) : 'not published: a reading is unavailable'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** 2 · Source × sink — every right ribbon as a cell. */
function Matrix({s, norm, basis, focus, onFocus}: Props) {
  if (!s.provenance) {
    return <p className={styles.empty}>No provenance this snapshot: a reading is unavailable.</p>;
  }
  if (!s.sources.length || !s.sinks.length) {
    return <p className={styles.empty}>Nothing flows from a source to a sink in this snapshot.</p>;
  }
  return (
    <table className={clsx(styles.table, styles.matrix)}>
      <thead>
        <tr>
          <th className={styles.firstCol}>Source ↓ · sink →</th>
          {s.sinks.map((k) => (
            <th key={k.uid}>
              <span className={styles.swatch} style={{background: k.color}} />
              {k.uid}
            </th>
          ))}
          <th className={clsx(styles.num, styles.totalCol)}>Total</th>
        </tr>
      </thead>
      <tbody>
        {s.sources.map((src) => (
          <tr key={src.uid}>
            <td className={styles.strong}>
              <span className={styles.swatch} style={{background: src.color}} />
              {src.uid}
            </td>
            {s.sinks.map((k) => {
              const r = s.right.find((x) => x.src === src.uid && x.sink === k.uid);
              if (!r) {
                const ok = allowed(s, src.uid, k.uid);
                return (
                  <td key={k.uid} className={styles.zero}>
                    —{' '}
                    <span className={styles.cellSub}>
                      {ok ? '0 W' : k.kind === 'grid' ? 'cannot export' : 'not allowed'}
                    </span>
                  </td>
                );
              }
              const sub =
                norm === 'pctSink'
                  ? fmtPct(r.ofSink)
                  : norm === 'eur'
                    ? (() => {
                        const m = rightMoney(s, r, basis);
                        return m?.value ? fmtEur(m.value) : '';
                      })()
                    : fmtPct(r.ofSource);
              const bar = norm === 'pctSink' ? num(r.ofSink) : num(r.ofSource);
              return (
                <td
                  key={k.uid}
                  className={clsx(
                    focus?.id === r.id && styles.hl,
                    !allowed(s, src.uid, k.uid) && styles.warnCell,
                  )}
                  title={allowed(s, src.uid, k.uid) ? undefined : 'Relaxed restriction: configuration rules this source out'}
                  onPointerEnter={() => onFocus({type: 'link', id: r.id})}
                  onPointerLeave={() => onFocus(null)}
                >
                  <span className={styles.strong}>{fmtW(r.w)}</span>{' '}
                  <span className={styles.cellSub}>{sub}</span>
                  <span className={styles.cellTrack}>
                    <span style={{width: `${Math.min(bar, 1) * 100}%`, background: src.color}} />
                  </span>
                </td>
              );
            })}
            <td className={clsx(styles.num, styles.strong)}>
              {fmtW(src.flow)}
              {norm !== 'pctSink' && norm !== 'eur' && <span className={styles.cellSub}> 100%</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 3 · Per-source channels — the per-source channel power and ratio sensors. */
function PerSource({s, norm}: Props) {
  const chans = s.channels.map((c) => c.id);
  if (!chans.length) {
    return <p className={styles.empty}>No channel carries power in this snapshot.</p>;
  }
  const second = norm === 'pctSink' ? 'Share' : 'Ratio';
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Source</th>
          {chans.map((ch) => (
            <React.Fragment key={ch}>
              <th className={styles.num}>To {CHANNEL_TITLE[ch].toLowerCase()}</th>
              <th className={styles.num}>{second}</th>
            </React.Fragment>
          ))}
        </tr>
      </thead>
      <tbody>
        {s.sources.map((src) => (
          <tr key={src.uid}>
            <td className={styles.strong}>
              <span className={styles.swatch} style={{background: src.color}} />
              {src.uid}
            </td>
            {chans.map((ch: Channel) => {
              const w = value(s, `source_adapters_${ch}_power`, src.uid);
              const f = value(
                s,
                norm === 'pctSink' ? `source_adapters_${ch}_shares` : `source_adapters_${ch}_ratios`,
                src.uid,
              );
              const impossible = ch === 'export' && (src.kind === 'grid' || src.config.exports_power === false);
              return (
                <React.Fragment key={ch}>
                  <td className={clsx(styles.num, isZero(w) ? styles.zeroVal : styles.strong)}>
                    {impossible ? '—' : fmtW(w)}
                  </td>
                  <td className={clsx(styles.num, styles.mono)}>{impossible ? '' : f ? exact(f) ?? String(num(f)) : '—'}</td>
                </React.Fragment>
              );
            })}
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td className={styles.muted}>channel total</td>
          {s.channels.map((c) => (
            <React.Fragment key={c.id}>
              <td className={clsx(styles.num, styles.strong)}>{fmtW(c.w)}</td>
              <td />
            </React.Fragment>
          ))}
        </tr>
      </tfoot>
    </table>
  );
}

function fmtUnit(v: Frac | null, doc: PropertyDoc | undefined): string {
  switch (doc?.unit) {
    case 'share':
    case 'ratio':
      return pctExact(v);
    case 'EUR/h':
      return fmtEur(v);
    case 'EUR/kWh':
      return fmtEurKwh(v);
    default:
      return fmtW(v);
  }
}

function Leaf({v, doc}: {v: ValueTree; doc: PropertyDoc | undefined}) {
  if (v === null) {
    return <span className={styles.zeroVal}>unavailable</span>;
  }
  const f = frac(v as string);
  const e = doc?.unit === 'share' || doc?.unit === 'ratio' ? null : exact(f);
  return (
    <>
      {fmtUnit(f, doc)}
      {e && <span className={styles.frac}> = {e}</span>}
    </>
  );
}

function Tree({v, doc}: {v: ValueTree; doc: PropertyDoc | undefined}) {
  if (v === null || typeof v !== 'object') {
    return <Leaf v={v} doc={doc} />;
  }
  return (
    <span className={styles.tree}>
      {Object.entries(v).map(([k, inner]) => (
        <span key={k} className={styles.treeRow}>
          <span className={styles.mono}>{k}</span> <Tree v={inner} doc={doc} />
        </span>
      ))}
    </span>
  );
}

/** 4 · Every engine value — nothing the engine publishes is left off the page. */
function Everything({s}: Props) {
  const layers = s.catalog.layers ?? {};
  const byLayer = new Map<number, [string, ValueTree][]>();
  for (const r of s.state.results) {
    const layer = s.catalog.properties[r.property]?.layer ?? 1;
    byLayer.set(layer, [...(byLayer.get(layer) ?? []), [r.property, r.value]]);
  }
  return (
    <table className={clsx(styles.table, styles.everything)}>
      {[...byLayer.entries()]
        .sort(([a], [b]) => a - b)
        .map(([layer, rows]) => (
          <tbody key={layer}>
            <tr>
              <th colSpan={2}>
                {layer} · {layers[String(layer)] ?? `Layer ${layer}`}
              </th>
            </tr>
            {rows.map(([p, v]) => {
              const doc = s.catalog.properties[p];
              return (
                <tr key={p}>
                  <td>
                    <span title={doc?.definition}>{doc?.title ?? p}</span>
                    <span className={clsx(styles.mono, styles.propName)}>{p}</span>
                  </td>
                  <td className={styles.num}>
                    <Tree v={v} doc={doc} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        ))}
    </table>
  );
}
