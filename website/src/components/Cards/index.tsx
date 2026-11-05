import React, {type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import {useActiveVersion} from '@docusaurus/plugin-content-docs/client';
import styles from './styles.module.css';

type Accent = 'grid' | 'solar' | 'battery' | 'consumer' | 'neutral';

// A responsive grid of link/feature cards for landing and overview pages:
//   <CardGrid>
//     <Card title="Grid" icon="⚡" accent="grid" to="/devices/grid">…</Card>
//   </CardGrid>
// `to` without a leading slash is a doc id path ("installation"), resolved
// against the docs version being viewed so a card on /next stays on /next.
function useDocHref(to?: string): string | undefined {
  const version = useActiveVersion(undefined);
  if (!to || to.startsWith('/') || /^[a-z]+:/.test(to)) return to;
  if (!version) return to;
  return `${version.path.replace(/\/$/, '')}/${to}`;
}

export function ButtonLink({
  to,
  primary = false,
  children,
}: {
  to: string;
  primary?: boolean;
  children: ReactNode;
}) {
  const href = useDocHref(to)!;
  return (
    <Link
      to={href}
      className={`button button--lg ${primary ? 'button--primary' : 'button--secondary'}`}>
      {children}
    </Link>
  );
}

export function CardGrid({children}: {children: ReactNode}) {
  return <div className={styles.grid}>{children}</div>;
}

export function Card({
  title,
  icon,
  accent = 'neutral',
  to,
  children,
}: {
  title: string;
  icon?: string;
  accent?: Accent;
  to?: string;
  children?: ReactNode;
}) {
  const body = (
    <>
      <div className={styles.head}>
        {icon && (
          <span className={styles.icon} aria-hidden="true">
            {icon}
          </span>
        )}
        <span className={styles.title}>{title}</span>
      </div>
      {children && <div className={styles.body}>{children}</div>}
    </>
  );
  const href = useDocHref(to);
  const className = `${styles.card} ${styles[`accent-${accent}`]}`;
  return href ? (
    <Link to={href} className={`${className} ${styles.link}`}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}
