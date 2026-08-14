import React from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';
import type {Certification} from './types';

const TITLE: {[k: string]: string} = {
  verified: 'hand-certified: derived independently, and it agreed',
  disputed: 'hand-derived answer disagreed with the engine',
  unverified: 'engine-generated, not yet certified',
};

/**
 * Where a value came from. Deliberately small: a reader deserves to know which
 * numbers a human has checked, but the badge must not dominate the number.
 */
export default function CertDot({
  status = 'unverified',
}: {
  status?: Certification['status'];
}): React.ReactElement {
  return (
    <span
      className={clsx(
        styles.cert,
        status === 'verified' && styles.v,
        status === 'disputed' && styles.d,
      )}
      title={TITLE[status] ?? TITLE.unverified}
    />
  );
}
