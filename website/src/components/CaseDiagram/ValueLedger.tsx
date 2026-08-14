import React, {useState} from 'react';
import clsx from 'clsx';

import styles from './styles.module.css';
import CertDot from './CertDot';
import {fmtUnit, humanize} from './rational';
import {UNAVAILABLE} from './types';
import type {Expectation, PropertyCatalog, PropertyDoc, ValueTree} from './types';

/**
 * Every value the engine published for this snapshot, in one table.
 *
 * The graph can only ever re-label its nodes, so most of what the integration
 * computes — the channel ratios, the per-source attributions, the whole
 * monetary family — has nowhere to live on the picture. It lives here instead:
 * one row per published property, in the catalog's dependency order, with the
 * exact fraction next to the figure a reader intuits and a dot saying whether a
 * human has checked it.
 */

function scalarCell(
  stored: string | null,
  doc: PropertyDoc | undefined,
): React.ReactElement {
  // Two different nothings, and conflating them would be a lie in both
  // directions. A null slot is one nobody has derived — the corpus is silent,
  // not asserting anything. The unavailable marker is a derivation whose
  // answer *is* that the engine should report nothing.
  if (stored === null) {
    return <b className={styles.vpending}>not yet derived</b>;
  }
  if (stored === UNAVAILABLE) {
    return <b className={styles.vunavail}>unavailable</b>;
  }
  const {text, frac} = fmtUnit(stored, doc?.unit);
  return (
    <b>
      {text}
      {frac && <span className={styles.frac}>= {frac}</span>}
    </b>
  );
}

/** Sub-rows for a map value, and sub-groups for a nested one. */
function breakdown(
  value: ValueTree,
  doc: PropertyDoc | undefined,
): React.ReactElement {
  if (value === null) {
    return <div className={styles.vpending}>not yet derived</div>;
  }
  const entries = Object.entries(value as {[k: string]: ValueTree});
  if (!entries.length) {
    return <div className={styles.vnone}>none this snapshot</div>;
  }
  return (
    <div className={styles.vmap}>
      {entries.map(([key, inner]) =>
        inner !== null && typeof inner === 'object' ? (
          <div className={styles.vgroup} key={key}>
            <span className={styles.vkey}>{key}</span>
            {breakdown(inner, doc)}
          </div>
        ) : (
          <div className={styles.vrow} key={key}>
            <i>{key}</i>
            {scalarCell(inner as string | null, doc)}
          </div>
        ),
      )}
    </div>
  );
}

function Row({
  expectation,
  doc,
}: {
  expectation: Expectation;
  doc: PropertyDoc | undefined;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const {property, value, certification} = expectation;
  const isMap = value !== null && typeof value === 'object';
  const pending = value === null;
  const explainable = Boolean(doc?.definition);

  return (
    <div className={clsx(styles.prow, open && styles.on)}>
      <button
        type="button"
        className={styles.phead}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        disabled={!explainable}
      >
        <span className={styles.pname}>
          {explainable && <span className={styles.pchev} aria-hidden="true" />}
          {doc?.title ?? humanize(property)}
        </span>
        {(!isMap || pending) && scalarCell(value as string | null, doc)}
        <CertDot status={certification.status} />
      </button>
      {isMap && breakdown(value, doc)}
      {open && doc && (
        <div className={styles.pdef}>
          <p>{doc.definition}</p>
          {doc.formula && <code className={styles.pformula}>{doc.formula}</code>}
          {doc.note && <p className={styles.pnote}>{doc.note}</p>}
          <p className={styles.pprop}>
            <code>{property}</code>
          </p>
        </div>
      )}
    </div>
  );
}

export interface ValueLedgerProps {
  title: string;
  expectations: Expectation[];
  catalog: PropertyCatalog | undefined;
}

export default function ValueLedger({
  title,
  expectations,
  catalog,
}: ValueLedgerProps): React.ReactElement {
  return (
    <section className={styles.values} aria-label={`${title} — published values`}>
      <p className={styles.vtitle}>{title}</p>
      {expectations.length ? (
        expectations.map((e) => (
          <Row
            key={e.property}
            expectation={e}
            doc={catalog?.properties?.[e.property]}
          />
        ))
      ) : (
        <div className={styles.vnone}>
          This snapshot publishes nothing in this layer.
        </div>
      )}
    </section>
  );
}
