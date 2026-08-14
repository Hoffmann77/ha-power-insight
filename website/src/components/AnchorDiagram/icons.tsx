import React from 'react';
import type {NodeKind} from './types';

/**
 * Device glyphs, drawn on a -11..11 box so they drop into a node circle
 * unscaled. Colour comes from a CSS custom property rather than a literal, so
 * the palette flips with the site theme without any JavaScript.
 */

const PATHS: {[k in NodeKind]: React.ReactNode} = {
  grid: (
    <path
      d="M-5.5 9 L0 -9 L5.5 9 M-8 -2.5 L8 -2.5 M-6 -6 L6 -6 M-8 -2.5 L-3 3 M8 -2.5 L3 3"
      fill="none"
      strokeWidth="1.6"
    />
  ),
  pv: (
    <g fill="none" strokeWidth="1.6">
      <rect x="-9" y="-8" width="18" height="11" rx="1" />
      <path d="M-3 -8 V3 M3 -8 V3 M-9 -2.5 H9 M0 3 V8 M-4 8 H4" />
    </g>
  ),
  battery: (
    <g fill="none" strokeWidth="1.6">
      <rect x="-5" y="-6.5" width="10" height="15" rx="1.5" />
      <path d="M-2 -8.5 H2" />
      <path d="M-2.5 5 H2.5 M-2.5 1.5 H2.5" strokeWidth="1.4" />
    </g>
  ),
  consumer: (
    <path
      d="M2.5 -9 L-6 1.5 L-1 1.5 L-2.5 9 L6 -1.5 L1 -1.5 Z"
      fill="currentColor"
      stroke="none"
    />
  ),
  home: (
    <g fill="none" strokeWidth="1.6">
      <path d="M-9 0.5 L0 -8 L9 0.5" />
      <path d="M-6.5 -1.5 V8 H6.5 V-1.5" />
    </g>
  ),
};

/** The CSS custom property carrying this device kind's colour. */
export function kindColor(kind: NodeKind): string {
  return `var(--ad-c-${kind})`;
}

export const KIND_LABEL: {[k in NodeKind]: string} = {
  grid: 'Grid',
  pv: 'PV string',
  battery: 'Battery',
  consumer: 'Consumer',
  home: 'Home base load',
};

/** The glyph as a bare `<g>`, for use inside the diagram's own SVG. */
export function DeviceGlyph({kind}: {kind: NodeKind}): React.ReactElement {
  const color = kindColor(kind);
  return (
    <g
      stroke={color}
      style={{color}}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {PATHS[kind]}
    </g>
  );
}

/** A standalone icon, for the detail panel header. */
export function DeviceIcon({
  kind,
  size = 22,
}: {
  kind: NodeKind;
  size?: number;
}): React.ReactElement {
  return (
    <svg
      width={size}
      height={size}
      viewBox="-11 -11 22 22"
      aria-hidden="true"
      style={{flex: 'none'}}
    >
      <DeviceGlyph kind={kind} />
    </svg>
  );
}
