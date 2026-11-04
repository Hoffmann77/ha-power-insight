/**
 * Exact rationals for the few figures the chart derives from stored ones.
 *
 * Case files store every value as an exact rational string ("8/15", "-600") so
 * a reader can check it by hand. When the chart divides two of them — a ribbon
 * as a fraction of its source's output — the answer has to stay exact too,
 * or the "= 4/15" it prints would be a float's guess. BigInt keeps it exact.
 */

export interface Frac {
  n: bigint;
  d: bigint;
}

function gcd(a: bigint, b: bigint): bigint {
  let x = a < 0n ? -a : a;
  let y = b < 0n ? -b : b;
  while (y) {
    [x, y] = [y, x % y];
  }
  return x || 1n;
}

function norm(n: bigint, d: bigint): Frac {
  if (d === 0n) {
    throw new Error('division by zero');
  }
  if (d < 0n) {
    n = -n;
    d = -d;
  }
  const g = gcd(n, d);
  return {n: n / g, d: d / g};
}

/** Parse a stored rational. `null`/`undefined` stays absent. */
export function frac(s: string | null | undefined): Frac | null {
  if (s === null || s === undefined) {
    return null;
  }
  const [a, b] = String(s).split('/');
  return norm(BigInt(a), BigInt(b ?? '1'));
}

export const ZERO: Frac = {n: 0n, d: 1n};

export const add = (a: Frac, b: Frac): Frac => norm(a.n * b.d + b.n * a.d, a.d * b.d);
export const sub = (a: Frac, b: Frac): Frac => norm(a.n * b.d - b.n * a.d, a.d * b.d);
export const mul = (a: Frac, b: Frac): Frac => norm(a.n * b.n, a.d * b.d);
export const div = (a: Frac, b: Frac): Frac => norm(a.n * b.d, a.d * b.n);
export const abs = (a: Frac): Frac => ({n: a.n < 0n ? -a.n : a.n, d: a.d});
export const isZero = (a: Frac | null): boolean => !a || a.n === 0n;
export const sum = (xs: Frac[]): Frac => xs.reduce(add, ZERO);
export const cmp = (a: Frac, b: Frac): number => {
  const x = a.n * b.d - b.n * a.d;
  return x > 0n ? 1 : x < 0n ? -1 : 0;
};

export function num(a: Frac | null): number {
  return a ? Number(a.n) / Number(a.d) : 0;
}

/** "3/5", or "1" for a whole number. */
export function fracText(a: Frac): string {
  return a.d === 1n ? String(a.n) : `${a.n}/${a.d}`;
}

/** Watts at the precision a reader can act on: "480 W", "213.3 W". */
export function fmtW(a: Frac | null): string {
  if (!a) {
    return '—';
  }
  const v = num(a);
  if (Math.abs(v) >= 10000) {
    return `${(v / 1000).toFixed(1)} kW`;
  }
  return `${a.d === 1n ? v : Math.round(v * 10) / 10} W`;
}

/** "60%", with one decimal when it is not whole. */
export function fmtPct(a: Frac | null): string {
  if (!a) {
    return '—';
  }
  const p = num(a) * 100;
  return `${Number.isInteger(p) ? p : Math.round(p * 10) / 10}%`;
}

/** Euro per hour, as the engine's rate sensors are quoted. */
export function fmtEur(a: Frac | null): string {
  if (!a) {
    return '—';
  }
  const v = num(a);
  const r = Math.round(v * 1000) / 1000;
  return `${r === 0 && v !== 0 ? v.toPrecision(2) : r} €/h`;
}

/** Euro per kWh — a price, as opposed to a rate. */
export function fmtEurKwh(a: Frac | null): string {
  return a ? `${(Math.round(num(a) * 10000) / 10000).toFixed(4)} €/kWh` : '—';
}

/** The exact form worth printing beside a decimal, or null when it adds nothing. */
export function exact(a: Frac | null): string | null {
  return a && a.d !== 1n ? fracText(a) : null;
}
