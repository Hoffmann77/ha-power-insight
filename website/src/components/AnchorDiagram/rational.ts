/**
 * Exact-rational parsing and the display formats the diagram uses.
 *
 * Case files store "8/15" rather than 0.5333… so the published value stays the
 * one a reader can check by hand. The fraction is what someone verifies; the
 * decimal is what they intuit, so most surfaces show the decimal with the
 * fraction alongside.
 */

/** Parse a stored rational ("400", "-600", "8/15") to a number. */
export function rat(s: string | null | undefined): number {
  if (s === null || s === undefined) {
    return 0;
  }
  const text = String(s);
  const parts = text.split('/');
  if (parts.length === 2) {
    const den = Number(parts[1]);
    return den === 0 ? 0 : Number(parts[0]) / den;
  }
  return Number(text);
}

/** Watts, at the precision a reader can act on. */
export function fmtW(v: number): string {
  const a = Math.abs(v);
  if (a >= 10000) {
    return `${(v / 1000).toFixed(1)} kW`;
  }
  if (Number.isInteger(v)) {
    return `${v} W`;
  }
  return `${Math.round(v * 10) / 10} W`;
}

/** Euro per hour, the unit every monetary rate in the engine is quoted in. */
export function fmtEur(v: number): string {
  return `${Math.round(v * 1000) / 1000} €/h`;
}

export interface ShareDisplay {
  /** Decimal form, the primary display. */
  dec: string;
  /** The exact fraction, when the stored value had one. */
  frac: string | null;
  value: number;
}

export function fmtShare(s: string | null | undefined): ShareDisplay {
  const value = rat(s);
  return {
    dec: String(Math.round(value * 1000) / 1000),
    frac: s !== null && s !== undefined && String(s).includes('/') ? String(s) : null,
    value,
  };
}

/** `hall_tight_pair` -> `Hall tight pair`. */
export function humanize(id: string): string {
  const s = id.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
