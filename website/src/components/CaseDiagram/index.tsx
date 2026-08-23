import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {useHistory, useLocation} from '@docusaurus/router';
import clsx from 'clsx';

import styles from './styles.module.css';
import FlowSvg from './FlowSvg';
import ValueLedger from './ValueLedger';
import {LAYERS, groupByLayer, layerTitle} from './layers';
import {DeviceIcon, KIND_LABEL, kindColor} from './icons';
import {fmtEur, fmtPct, fmtShare, fmtW, humanize, rat} from './rational';
import {costOf, buildModel, hasValue, roleText} from './model';
import type {FlowEdge, FlowModel, FlowNode} from './model';
import type {
  AdapterConfig,
  LayerId,
  PropertyCatalog,
  ReferenceCase,
} from './types';

export interface CaseDiagramProps {
  /**
   * The one case this diagram draws. Cases are not switched inside the
   * component: each gets its own docs page, where the prose around it can say
   * what the wiring is for.
   */
  case: ReferenceCase;
  /** The property catalog, for titles, units and definitions in the table. */
  properties?: PropertyCatalog;
  /** Which snapshot to open on. Defaults to the case's first. */
  initialState?: string;
  /** Which layer to open on. Defaults to the readings. */
  initialLayer?: LayerId;
}

/**
 * Whether a stacked-bar segment can carry its label inside itself.
 *
 * A flat percentage threshold is not enough: the same 17% segment holds
 * "home · 200 W" and clips "home · 0.028 €/h". The bar is ~536 px at full
 * width, so a percent buys a little under one character.
 */
function fitsInline(label: string, pct: number): boolean {
  return pct >= 16 && label.length <= pct * 0.84;
}

/** How each config key is presented in the detail panel. */
function configRows(config: AdapterConfig): [string, string, string | null][] {
  const rows: [string, string, string | null][] = [];
  const frac = (v: string | null | undefined) =>
    v && String(v).includes('/') ? String(v) : null;

  if (config.has_price_entity !== undefined) {
    rows.push(['Price entity', config.has_price_entity ? 'yes' : 'no', null]);
  }
  if (config.lcoe !== undefined) {
    rows.push(['LCOE', `${fmtShare(config.lcoe).dec} €/kWh`, frac(config.lcoe)]);
  }
  if (config.lcos !== undefined) {
    rows.push(['LCOS', `${fmtShare(config.lcos).dec} €/kWh`, frac(config.lcos)]);
  }
  if (config.lco2_intensity !== undefined) {
    rows.push(['LCO₂', `${config.lco2_intensity} g/kWh`, null]);
  }
  if (config.exports_power !== undefined) {
    rows.push(['May export', config.exports_power ? 'yes' : 'no', null]);
  }
  if (config.export_compensation !== undefined) {
    rows.push([
      'Export comp.',
      `${fmtShare(config.export_compensation).dec} €/kWh`,
      frac(config.export_compensation),
    ]);
  }
  if (config.correction_factor !== undefined) {
    rows.push([
      'Correction factor',
      fmtShare(config.correction_factor).dec,
      null,
    ]);
  }
  if (config.charge_from_adapters !== undefined) {
    rows.push([
      'May charge from',
      config.charge_from_adapters.length
        ? config.charge_from_adapters.join(', ')
        : 'unrestricted',
      null,
    ]);
  }
  if (config.power_from_adapters !== undefined) {
    rows.push([
      'May draw from',
      config.power_from_adapters.length
        ? config.power_from_adapters.join(', ')
        : 'unrestricted',
      null,
    ]);
  }
  return rows;
}

export default function CaseDiagram({
  case: refCase,
  properties,
  initialState,
  initialLayer = '1',
}: CaseDiagramProps): React.ReactElement | null {
  const history = useHistory();
  const location = useLocation();

  const [stateId, setStateId] = useState(
    () =>
      (initialState && refCase.states.some((s) => s.id === initialState)
        ? initialState
        : refCase.states[0]?.id) ?? '',
  );
  const [layer, setLayer] = useState<LayerId>(initialLayer);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [urlApplied, setUrlApplied] = useState(false);

  // Deep links. Read the query only after mount so the server-rendered markup
  // and the first client render agree; write it back on every change so a
  // reader can link someone at exactly the snapshot they mean.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wantState = params.get('state');
    if (wantState && refCase.states.some((s) => s.id === wantState)) {
      setStateId(wantState);
    }
    setUrlApplied(true);
    // Mount only: later changes are pushed out by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!urlApplied || !stateId) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get('state') === stateId) {
      return;
    }
    params.set('state', stateId);
    history.replace({...location, search: `?${params.toString()}`});
    // `location` intentionally omitted: including it re-fires on our own write.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateId, urlApplied, history]);

  const activeState = useMemo(
    () => refCase.states.find((s) => s.id === stateId) ?? refCase.states[0],
    [refCase, stateId],
  );

  const model: FlowModel | null = useMemo(
    () => (activeState ? buildModel(refCase, activeState) : null),
    [refCase, activeState],
  );

  const byLayer = useMemo(
    () => (activeState ? groupByLayer(activeState.expectations, properties) : null),
    [activeState, properties],
  );

  const pickState = useCallback((id: string) => {
    setStateId(id);
    setSelectedUid(null);
  }, []);

  const clearSelection = useCallback(() => setSelectedUid(null), []);

  // Clicking the focused device unfocuses it; clicking another moves the focus.
  const toggleNode = useCallback((uid: string) => {
    setSelectedUid((current) => (current === uid ? null : uid));
  }, []);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        setSelectedUid(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!activeState || !model || !byLayer) {
    return null;
  }

  const selected: FlowNode | null =
    model.nodes.find((n) => n.uid === selectedUid) ?? null;

  const stateDerived = activeState.expectations.length;

  /** A stacked supply or demand bar, valued in whatever the layer asks for. */
  const ledgerRow = (title: string, list: FlowNode[]) => {
    // A node with no reading contributes nothing to the bar rather than a
    // zero-width segment: the home base load has no derived size yet on most
    // snapshots, and it must not be drawn as though it were measured at zero.
    const watts = (n: FlowNode) => (n.reading === null ? 0 : Math.abs(n.reading));
    const totalW = list.reduce((a, n) => a + watts(n), 0);
    if (!totalW) {
      return (
        <div className={styles.lrow} key={title}>
          <div className={styles.lhead}>
            <span>{title}</span>
          </div>
          <div className={styles.lempty}>nothing attributable this snapshot</div>
        </div>
      );
    }
    const segValue = (n: FlowNode) =>
      layer === '4'
        ? fmtEur(costOf(model, n))
        : layer === '2'
          ? fmtPct(watts(n) / totalW)
          : fmtW(n.reading === null ? null : Math.abs(n.reading));
    const totalLabel =
      layer === '4'
        ? fmtEur(list.reduce((a, n) => a + costOf(model, n), 0))
        : layer === '2'
          ? '100%'
          : fmtW(totalW);
    const segLabel = (n: FlowNode) => `${n.uid} · ${segValue(n)}`;
    const pctOf = (n: FlowNode) => (watts(n) / totalW) * 100;
    const smalls = list.filter((n) => !fitsInline(segLabel(n), pctOf(n)));
    return (
      <div className={styles.lrow} key={title}>
        <div className={styles.lhead}>
          <span>{title}</span>
          <b>{totalLabel}</b>
        </div>
        <div className={styles.lbar}>
          {list.map((n) => {
            const pct = pctOf(n);
            return (
              <i
                key={n.uid}
                style={{width: `${pct}%`, background: kindColor(n.kind)}}
                title={segLabel(n)}
              >
                {fitsInline(segLabel(n), pct) && <span>{segLabel(n)}</span>}
              </i>
            );
          })}
        </div>
        {smalls.length > 0 && (
          <div className={styles.lleg}>
            {smalls.map((n) => (
              <span key={n.uid}>
                <span
                  className={styles.ldot}
                  style={{background: kindColor(n.kind)}}
                />
                {n.uid} <b>{segValue(n)}</b>
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  /** Layer 3's headline: where the gross power actually went. */
  const channelRow = () => {
    if (!model.channels.length) {
      return (
        <div className={styles.lrow}>
          <div className={styles.lhead}>
            <span>Channel split</span>
            <b>{fmtW(model.gross)} gross</b>
          </div>
          <div className={styles.lempty}>
            Gross power is zero, so there is nothing to split.
          </div>
        </div>
      );
    }
    return (
      <div className={styles.lrow}>
        <div className={styles.lhead}>
          <span>Channel split of gross power</span>
          <b>{fmtW(model.gross)}</b>
        </div>
        <div className={styles.lbar}>
          {model.channels.map((c) => {
            const label = `${c.label} · ${fmtPct(c.value)}`;
            return (
              <i
                key={c.channel}
                className={styles[`ch_${c.channel}`]}
                style={{width: `${c.value * 100}%`}}
                title={`${label} = ${c.ratio}`}
              >
                {fitsInline(label, c.value * 100) && <span>{label}</span>}
              </i>
            );
          })}
        </div>
        <div className={styles.lleg}>
          {model.channels
            .filter(
              (c) => !fitsInline(`${c.label} · ${fmtPct(c.value)}`, c.value * 100),
            )
            .map((c) => (
              <span key={c.channel}>
                <span
                  className={clsx(styles.ldot, styles[`ch_${c.channel}`])}
                />
                {c.label} <b>{fmtPct(c.value)}</b>
              </span>
            ))}
        </div>
      </div>
    );
  };

  const flowRows = (edges: FlowEdge[], dir: 'from' | 'to', magnitude: number) => {
    if (!edges.length) {
      return (
        <div className={styles.kv}>
          <i>No attributable flow</i>
          <b>—</b>
        </div>
      );
    }
    return edges.map((e) => {
      const other = dir === 'from' ? e.from : e.to;
      const share = e.share
        ? fmtShare(e.share)
        : {dec: (e.w / magnitude).toFixed(3), frac: null, value: e.w / magnitude};
      const otherKind =
        model.nodes.find((n) => n.uid === other)?.kind ?? 'home';
      return (
        <div className={styles.flowrow} key={`${e.from}->${e.to}`}>
          <div className={styles.fl}>
            <span>
              {dir === 'from' ? '← ' : '→ '}
              {other}
            </span>
            <b>
              {fmtW(e.w)}
              <span className={styles.frac}>
                {share.dec}
                {share.frac ? ` = ${share.frac}` : ''}
              </span>
            </b>
          </div>
          <div className={styles.bar}>
            <i
              style={{
                width: `${Math.round(share.value * 100)}%`,
                background: kindColor(otherKind),
                opacity: 0.55,
              }}
            />
          </div>
        </div>
      );
    });
  };

  const sharesDerived = hasValue(
    model.byProperty,
    selected?.virtual
      ? 'home_base_load_source_shares'
      : 'sink_adapters_source_shares',
  );

  return (
    <div className={styles.root}>
      <div className={styles.scards}>
        {refCase.states.map((s, i) => {
          const open = Boolean(s.open_question);
          return (
            <button
              type="button"
              key={s.id}
              className={clsx(styles.scard, s.id === activeState.id && styles.on)}
              onClick={() => pickState(s.id)}
            >
              {open && <span className={styles.scq} title="open modelling question" />}
              <span className={styles.sctitle}>
                <span className={styles.scnum}>{`0${i + 1}`}</span>
                {humanize(s.id)}
                {open && <span className={styles.scqlab}>OPEN Q</span>}
              </span>
              <span className={styles.scnote}>{s.note}</span>
            </button>
          );
        })}
      </div>

      <div className={styles.metricrow} role="tablist" aria-label="Engine layer">
        {LAYERS.map((l) => (
          <button
            type="button"
            key={l.id}
            role="tab"
            aria-selected={layer === l.id}
            title={layerTitle(l.id, properties)}
            className={clsx(styles.metric, layer === l.id && styles.on)}
            onClick={() => setLayer(l.id)}
          >
            {l.short}
          </button>
        ))}
      </div>

      <div className={styles.ledger}>
        {layer === '3'
          ? channelRow()
          : [
              ledgerRow('Supply', model.nodes.filter((n) => n.role === 'source')),
              ledgerRow('Demand', model.nodes.filter((n) => n.role === 'sink')),
            ]}
      </div>

      <FlowSvg
        model={model}
        layer={layer}
        selected={selected}
        onSelect={toggleNode}
        onClear={clearSelection}
      />

      {selected && (
        <div className={styles.panel} role="region" aria-label="Device detail">
          <div className={styles.ph}>
            <DeviceIcon kind={selected.kind} />
            <span className={styles.uid}>{selected.uid}</span>
            <span className={styles.kindlab}>
              {KIND_LABEL[selected.kind]}
              {selected.virtual ? ' · virtual node' : ''}
            </span>
            <span
              className={styles.role}
              style={{
                background:
                  selected.role === 'idle' ? 'var(--cd-mut)' : kindColor(selected.kind),
              }}
            >
              {roleText(selected)}
            </span>
            <button
              type="button"
              className={styles.px}
              onClick={clearSelection}
              aria-label="Close device detail"
            >
              ×
            </button>
          </div>
          <div className={styles.pb}>
            <div className={styles.pcol}>
              <p className={styles.ptitle}>Configuration</p>
              {selected.virtual ? (
                <>
                  <div className={styles.kv}>
                    <i>Device</i>
                    <b>none — unmetered remainder</b>
                  </div>
                  <div className={styles.kv}>
                    <i>Defined as</i>
                    <b style={{fontWeight: 400}}>
                      everything consumed without a sensor on it
                    </b>
                  </div>
                </>
              ) : (
                configRows(selected.config ?? {}).map(([label, value, frac]) => (
                  <div className={styles.kv} key={label}>
                    <i>{label}</i>
                    <b>
                      {value}
                      {frac && <span className={styles.frac}>= {frac}</span>}
                    </b>
                  </div>
                ))
              )}
              <p className={styles.ptitle} style={{marginTop: 10}}>
                This snapshot
              </p>
              <div className={styles.kv}>
                <i>Reading</i>
                <b>
                  {selected.virtual
                    ? `${fmtW(
                        selected.reading === null
                          ? null
                          : Math.abs(selected.reading),
                      )} (derived)`
                    : fmtW(selected.reading)}
                </b>
              </div>
              <div className={styles.kv}>
                <i>Role</i>
                <b>{roleText(selected)}</b>
              </div>
              {selected.channel && (
                <div className={styles.kv}>
                  <i>Channel</i>
                  <b>{selected.channel}</b>
                </div>
              )}
            </div>
            <div className={styles.pcol}>
              {selected.role === 'sink' && (
                <>
                  <p className={styles.ptitle}>
                    Where its power came from{' '}
                    {!sharesDerived && (
                      <span className={styles.vpending}>not yet derived</span>
                    )}
                  </p>
                  {flowRows(
                    model.edges.filter((e) => e.to === selected.uid),
                    'from',
                    selected.reading === null ? 0 : Math.abs(selected.reading),
                  )}
                </>
              )}
              {selected.role === 'source' && (
                <>
                  <p className={styles.ptitle}>
                    Where its output went{' '}
                    {!sharesDerived && (
                      <span className={styles.vpending}>not yet derived</span>
                    )}
                  </p>
                  {flowRows(
                    model.edges.filter((e) => e.from === selected.uid),
                    'to',
                    selected.reading ?? 0,
                  )}
                </>
              )}
              {selected.role === 'idle' && (
                <>
                  <p className={styles.ptitle}>Flows</p>
                  <div className={styles.kv}>
                    <i>Idle this snapshot</i>
                    <b>—</b>
                  </div>
                </>
              )}
              {model.deficits[selected.uid] && (
                <div className={styles.alert}>
                  <b>
                    Restriction deficit: {fmtW(rat(model.deficits[selected.uid]))}.
                  </b>{' '}
                  Captive demand exceeded the local supply this device may legally
                  use.
                  {activeState.open_question
                    ? ' Which sink yields is an open modelling question — this allocation is one defensible answer, not settled spec.'
                    : ''}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <ValueLedger
        title={`${layer} · ${layerTitle(layer, properties)}`}
        expectations={byLayer[layer]}
        catalog={properties}
      />

      <p className={styles.certline}>
        {stateDerived === 1
          ? '1 value derived by hand for this snapshot'
          : `${stateDerived} values derived by hand for this snapshot`}
      </p>
    </div>
  );
}
