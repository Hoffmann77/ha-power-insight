import React from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';

const TITLE = {
  derived: 'derived by hand from the model, and asserted against the engine in CI',
  pending: 'not yet derived — no value is published for this slot',
};

/**
 * Whether a human has worked this value out. Deliberately small: a reader
 * deserves to know which numbers have been checked, but the badge must not
 * dominate the number.
 *
 * There are two states and no third. A derived value is one the engine is held
 * to on every commit, so a disagreement between the two never survives long
 * enough to need publishing — it is a red build, resolved by fixing whichever
 * of the code and the derivation turns out to be wrong.
 */
export default function CertDot({
  derived = false,
}: {
  derived?: boolean;
}): React.ReactElement {
  return (
    <span
      className={clsx(styles.cert, derived && styles.v)}
      title={derived ? TITLE.derived : TITLE.pending}
    />
  );
}
