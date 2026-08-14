import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {useHistory, useLocation} from '@docusaurus/router';
import clsx from 'clsx';

import styles from './styles.module.css';
import FlowSvg from './FlowSvg';
import {DeviceIcon, KIND_LABEL, kindColor} from './icons';
import {fmtEur, fmtShare, fmtW, humanize, rat} from './rational';
import {
  buildModel,
  certCounts,
  costOf,
  isVerified,
  roleText,
} from './model';
import type {FlowEdge, FlowModel, FlowNode} from './model';
import type {AdapterConfig, AnchorCase, Metric} from './types';

export interface AnchorDiagramProps {
  /** Every case the index should offer. Pass them all; the navbar switches. */
  cases: AnchorCase[];
  /** Which case to open on. Defaults to the first. */
  initialCase?: string;
  /** Which state to open on. Defaults to the case's first. */
  initialState?: string;
}

const METRICS: [Metric, string][] = [
  ['power', 'Power W'],
  ['shares', 'Shares'],
  ['cost', 'Cost €/h'],
];

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

function CertDot({verified}: {verified: boolean}): React.ReactElement {
  return (
    <span
      className={clsx(styles.cert, verified && styles.v)}
      title={verified ? 'hand-certified' : 'engine-generated, not yet certified'}
    />
  );
}

export default function AnchorDiagram({
  cases,
  initialCase,
  initialState,
}: AnchorDiagramProps): React.ReactElement | null {
  const history = useHistory();
  const location = useLocation();

  const firstCase = cases[0];
  const [caseId, setCaseId] = useState(
    () => (initialCase && cases.some((c) => c.id === initialCase) ? initialCase : firstCase?.id) ?? '',
  );
  const activeCase = cases.find((c) => c.id === caseId) ?? firstCase;

  const [stateId, setStateId] = useState(
    () =>
      (initialState &&
      activeCase?.states.some((s) => s.id === initialState)
        ? initialState
        : activeCase?.states[0]?.id) ?? '',
  );
  const [metric, setMetric] = useState<Metric>('power');
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [urlApplied, setUrlApplied] = useState(false);

  // Deep links. Read the query only after mount so the server-rendered markup
  // and the first client render agree; write it back on every change so a
  // reader can link someone at exactly the snapshot they mean.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wantCase = params.get('case');
    const wantState = params.get('state');
    const target = cases.find((c) => c.id === wantCase);
    if (target) {
      setCaseId(target.id);
      const st = target.states.find((s) => s.id === wantState);
      setStateId(st ? st.id : target.states[0].id);
    } else if (wantState) {
      const owner = cases.find((c) => c.states.some((s) => s.id === wantState));
      if (owner) {
        setCaseId(owner.id);
        setStateId(wantState);
      }
    }
    setUrlApplied(true);
    // Mount only: later changes are pushed out by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!urlApplied || !caseId || !stateId) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get('case') === caseId && params.get('state') === stateId) {
      return;
    }
    params.set('case', caseId);
    params.set('state', stateId);
    history.replace({...location, search: `?${params.toString()}`});
    // `location` intentionally omitted: including it re-fires on our own write.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, stateId, urlApplied, history]);

  const activeState = useMemo(
    () =>
      activeCase?.states.find((s) => s.id === stateId) ?? activeCase?.states[0],
    [activeCase, stateId],
  );

  const model: FlowModel | null = useMemo(
    () => (activeCase && activeState ? buildModel(activeCase, activeState) : null),
    [activeCase, activeState],
  );

  const pickCase = useCallback(
    (id: string) => {
      const target = cases.find((c) => c.id === id);
      if (!target) {
        return;
      }
      setCaseId(target.id);
      setStateId(target.states[0].id);
      setSelectedUid(null);
    },
    [cases],
  );

  const pickState = useCallback((id: string) => {
    setStateId(id);
    setSelectedUid(null);
  }, []);

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

  if (!activeCase || !activeState || !model) {
    return null;
  }

  const selected: FlowNode | null =
    model.nodes.find((n) => n.uid === selectedUid) ?? null;
  const [verified, total] = certCounts(activeCase);

  const ledgerRow = (title: string, list: FlowNode[]) => {
    const totalW = list.reduce((a, n) => a + Math.abs(n.reading), 0);
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
      metric === 'cost'
        ? fmtEur(costOf(model, n))
        : metric === 'shares'
          ? (Math.round((Math.abs(n.reading) / totalW) * 100) / 100).toFixed(2)
          : fmtW(Math.abs(n.reading));
    const totalLabel =
      metric === 'cost'
        ? fmtEur(list.reduce((a, n) => a + costOf(model, n), 0))
        : metric === 'shares'
          ? '1.00'
          : fmtW(totalW);
    const smalls = list.filter((n) => (Math.abs(n.reading) / totalW) * 100 < 16);
    return (
      <div className={styles.lrow} key={title}>
        <div className={styles.lhead}>
          <span>{title}</span>
          <b>{totalLabel}</b>
        </div>
        <div className={styles.lbar}>
          {list.map((n) => {
            const pct = (Math.abs(n.reading) / totalW) * 100;
            return (
              <i
                key={n.uid}
                style={{width: `${pct}%`, background: kindColor(n.kind)}}
                title={`${n.uid} · ${segValue(n)}`}
              >
                {pct >= 16 && <span>{`${n.uid} · ${segValue(n)}`}</span>}
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

  const sharesVerified = isVerified(
    model.byProperty,
    selected?.virtual
      ? 'home_base_load_source_shares'
      : 'sink_adapters_source_shares',
  );

  return (
    <div className={styles.root}>
      <div className={styles.idx}>
        {cases.map((c) => (
          <button
            type="button"
            key={c.id}
            className={clsx(styles.caseBtn, c.id === activeCase.id && styles.on)}
            onClick={() => pickCase(c.id)}
          >
            <b>{c.id}</b>
            {c.title}
          </button>
        ))}
      </div>

      <div className={styles.scards}>
        {activeCase.states.map((s, i) => {
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

      <div className={styles.metricrow} role="tablist" aria-label="Value category">
        <span className={styles.mlab}>view</span>
        {METRICS.map(([id, label]) => (
          <button
            type="button"
            key={id}
            role="tab"
            aria-selected={metric === id}
            className={clsx(styles.metric, metric === id && styles.on)}
            onClick={() => setMetric(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.ledger}>
        {ledgerRow(
          'Supply',
          model.nodes.filter((n) => n.role === 'source'),
        )}
        {ledgerRow(
          'Demand',
          model.nodes.filter((n) => n.role === 'sink'),
        )}
      </div>

      <FlowSvg
        model={model}
        metric={metric}
        selected={selected}
        onSelect={toggleNode}
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
                  selected.role === 'idle' ? 'var(--ad-mut)' : kindColor(selected.kind),
              }}
            >
              {roleText(selected)}
            </span>
            <button
              type="button"
              className={styles.px}
              onClick={() => setSelectedUid(null)}
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
                    ? `${fmtW(Math.abs(selected.reading))} (derived)`
                    : fmtW(selected.reading)}
                </b>
              </div>
              <div className={styles.kv}>
                <i>Role</i>
                <b>{roleText(selected)}</b>
              </div>
            </div>
            <div className={styles.pcol}>
              {selected.role === 'sink' && (
                <>
                  <p className={styles.ptitle}>
                    Where its power came from <CertDot verified={sharesVerified} />
                  </p>
                  {flowRows(
                    model.edges.filter((e) => e.to === selected.uid),
                    'from',
                    Math.abs(selected.reading),
                  )}
                </>
              )}
              {selected.role === 'source' && (
                <>
                  <p className={styles.ptitle}>
                    Where its output went <CertDot verified={sharesVerified} />
                  </p>
                  {flowRows(
                    model.edges.filter((e) => e.from === selected.uid),
                    'to',
                    selected.reading,
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

      <div className={styles.legend}>
        <span>
          click a device to focus · focused view shows the power exchanged with it
          · grey dash = allowed but unused source
        </span>
        <span>edge width ∝ watts · colour = source</span>
        <span>dashed ring = virtual node</span>
        <span>
          <CertDot verified={false} /> unverified · <CertDot verified /> verified
        </span>
        <span>
          {verified} of {total} values certified
        </span>
      </div>
    </div>
  );
}
