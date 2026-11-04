import React, {useCallback, useEffect, useId, useMemo, useRef, useState} from 'react';
import clsx from 'clsx';

import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-sans/latin-700.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-600.css';

import styles from './styles.module.css';
import Chart from './Chart';
import DataTable from './DataTable';
import {fmtW} from './fraction';
import {pathOf, tipFor, type Focus, type Norm} from './focus';
import {NARROW, WIDE, layout} from './layout';
import {buildSnapshot, type Basis} from './model';
import type {PropertyCatalog, ReferenceCase, SensorMap} from './types';

/**
 * One snapshot of a reference case, as a Sankey: sources → the four channels
 * of gross power → sinks, with the engine's own values in a table underneath.
 *
 * Everything comes from props — the case JSON, the property catalog and the
 * sensor map — imported at build time by the page, so an old docs version
 * keeps rendering its own engine's numbers. The layout is pure arithmetic and
 * the whole card server-renders; JavaScript only adds hover, focus and the
 * switches. Ribbon widths are watts in every view: the normalization switch
 * changes labels, never geometry, and the €/h view reads engine rates only.
 */

const NORMS: {id: Norm; symbol: string; caption: string}[] = [
  {id: 'watts', symbol: 'W', caption: 'Watts'},
  {id: 'pctSource', symbol: '%', caption: 'of source'},
  {id: 'pctSink', symbol: '%', caption: 'of sink'},
  {id: 'eur', symbol: '€/h', caption: 'cost rate'},
];

export interface FlowSankeyProps {
  case: ReferenceCase;
  /** The snapshot to draw, by id. */
  state: string;
  properties: PropertyCatalog;
  sensors: SensorMap;
  /** Optional heading inside the card; pages usually give the snapshot its own. */
  title?: string;
}

type At = {x: number; y: number} | Element | null;

export default function FlowSankey({
  case: refCase,
  state: stateId,
  properties,
  sensors,
  title,
}: FlowSankeyProps): React.ReactElement {
  const state = refCase.states.find((s) => s.id === stateId);
  if (!state) {
    // A typo in a page is a build-time failure, not an empty card.
    throw new Error(`FlowSankey: ${refCase.id} has no snapshot "${stateId}"`);
  }
  const s = useMemo(
    () => buildSnapshot(refCase, state, properties, sensors),
    [refCase, state, properties, sensors],
  );
  const wide = useMemo(() => layout(s, WIDE), [s]);
  const narrow = useMemo(() => layout(s, NARROW), [s]);

  const [norm, setNorm] = useState<Norm>('watts');
  const [basis, setBasis] = useState<Basis>('levelized');
  const [hover, setHover] = useState<Focus>(null);
  const [pinned, setPinned] = useState<Focus>(null);
  const [tipAt, setTipAt] = useState<{x: number; y: number} | null>(null);
  const area = useRef<HTMLDivElement>(null);
  const idp = `fs${useId().replace(/[^a-zA-Z0-9]/g, '')}`;

  const focus = hover ?? pinned;
  const path = useMemo(() => pathOf(s, focus), [s, focus]);
  const tip = useMemo(() => tipFor(s, focus, basis), [s, focus, basis]);

  const place = useCallback((at: At) => {
    const box = area.current?.getBoundingClientRect();
    if (!box || !at) {
      return;
    }
    if (at instanceof Element) {
      const r = at.getBoundingClientRect();
      setTipAt({x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top});
    } else {
      setTipAt({x: at.x - box.left, y: at.y - box.top});
    }
  }, []);

  const onHover = useCallback(
    (f: Focus, at: At) => {
      setHover(f);
      if (f) {
        place(at);
      }
    },
    [place],
  );
  const onPin = useCallback((f: Focus) => setPinned(f), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPinned(null);
        setHover(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const width = area.current?.clientWidth ?? 880;
  const tipStyle = tipAt
    ? {
        left: Math.max(8, Math.min(tipAt.x + 14, width - 258)),
        top: tipAt.y + 16,
      }
    : undefined;

  const missing = s.unavailable.map((d) => d.uid);
  const notice = !s.provenance
    ? `${missing.join(', ')} ${missing.length === 1 ? 'has' : 'have'} no reading, so the engine publishes no flows for this snapshot.`
    : null;

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <div>
          <div className={styles.kicker}>
            {s.caseTitle} · snapshot {String(s.index + 1).padStart(2, '0')}
          </div>
          {title && <div className={styles.title}>{title}</div>}
          <p className={styles.lede}>{s.state.note}</p>
        </div>
        <div className={styles.switches}>
          <div className={styles.switch} role="radiogroup" aria-label="Label ribbons with">
            {NORMS.map((n) => (
              <button
                key={n.id}
                type="button"
                role="radio"
                aria-checked={norm === n.id}
                className={clsx(styles.seg, norm === n.id && styles.on)}
                onClick={() => setNorm(n.id)}
              >
                <span className={styles.segSymbol}>{n.symbol}</span>
                <span className={styles.segCaption}>{n.caption}</span>
              </button>
            ))}
          </div>
          {norm === 'eur' && (
            <div className={styles.basis} role="radiogroup" aria-label="Price basis">
              {(['market', 'levelized'] as Basis[]).map((b) => (
                <button
                  key={b}
                  type="button"
                  role="radio"
                  aria-checked={basis === b}
                  className={clsx(styles.basisSeg, basis === b && styles.on)}
                  onClick={() => setBasis(b)}
                >
                  {b === 'market' ? 'Market' : 'Levelized'}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {s.state.open_question && (
        <div className={styles.question}>
          <b>Open question.</b> {s.state.open_question}
        </div>
      )}
      {notice && !wide.empty && <div className={styles.notice}>{notice}</div>}

      <div className={styles.area} ref={area}>
        {wide.empty ? (
          <div className={styles.emptyChart}>
            {s.provenance ? 'Every reading is 0 W, so nothing flows in this snapshot.' : notice}
          </div>
        ) : (
          <>
            <Chart
              s={s}
              lay={wide}
              vertical={false}
              norm={norm}
              basis={basis}
              path={path}
              pinned={pinned}
              idp={`${idp}w`}
              onHover={onHover}
              onPin={onPin}
            />
            <Chart
              s={s}
              lay={narrow}
              vertical
              norm={norm}
              basis={basis}
              path={path}
              pinned={pinned}
              idp={`${idp}n`}
              onHover={onHover}
              onPin={onPin}
            />
          </>
        )}
        {tip && tipStyle && (
          <div className={styles.tip} style={tipStyle} role="tooltip">
            <div className={styles.tipTitle}>
              {tip.title}
              {tip.on && <span className={styles.tipOn}> on {tip.on}</span>}
            </div>
            <div className={styles.tipPath}>{tip.path}</div>
            <div className={styles.tipGrid}>
              {tip.rows.map((r) => (
                <React.Fragment key={r.label}>
                  <span className={clsx(r.derived && styles.tipDerived)}>
                    {r.label}
                    {r.sensor && <span className={styles.tipSensor}>{r.sensor}</span>}
                  </span>
                  <span>
                    <b>{r.value}</b>
                    {r.exact && <span className={styles.frac}> = {r.exact}</span>}
                  </span>
                </React.Fragment>
              ))}
            </div>
            {tip.note && <div className={styles.tipNote}>{tip.note}</div>}
          </div>
        )}
      </div>

      <DataTable s={s} norm={norm} basis={basis} focus={focus} onFocus={setHover} />

      <div className={styles.foot}>
        {s.idle.length > 0 && (
          <span>
            Idle: {s.idle.map((d) => `${d.uid} · 0 W`).join(', ')}
          </span>
        )}
        {s.imbalance && s.imbalance.n > 0n && (
          <span>
            <i className={styles.hatchKey} /> {fmtW(s.imbalance)} of the readings is not explained
            by the other meters (hatched); the ribbons follow the engine&apos;s balanced flows.
          </span>
        )}
        {s.broken.length > 0 && (
          <span>
            <b className={styles.warnText}>▲</b> a restriction is relaxed: the readings cannot be
            met without it.
          </span>
        )}
        <span>
          {norm === 'eur'
            ? 'Every €/h figure is an engine value; nothing is priced in the browser. Market and Levelized read different engine families.'
            : 'Ribbon widths are watts in every view. Hover, focus or tap a ribbon to see the sensor behind it.'}
        </span>
      </div>
    </div>
  );
}
