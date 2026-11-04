/**
 * What a hovered (or focused, or tapped) ribbon or node means: which other
 * ribbons belong to its path, what its end labels say under the current
 * normalization, and what its tooltip shows — the Home Assistant sensor behind
 * the value first, then its figures.
 */
import {abs, exact, fmtEur, fmtPct, fmtW, type Frac} from './fraction';
import {
  CHANNEL_TITLE,
  channelMoney,
  deviceOf,
  leftMoney,
  named,
  nodeMoney,
  rightMoney,
  type Basis,
  type LeftLink,
  type RightLink,
  type Snapshot,
} from './model';
import type {Channel} from './types';

export type Norm = 'watts' | 'pctSource' | 'pctSink' | 'eur';

export type Focus = {type: 'link' | 'node'; id: string} | null;

/** Every link and node id on the path through `f`. */
export function pathOf(s: Snapshot, f: Focus): Set<string> | null {
  if (!f) {
    return null;
  }
  const on = new Set<string>([f.id]);
  const addLeft = (l: LeftLink) => on.add(l.id).add(`S:${l.src}`).add(`C:${l.channel}`);
  const addRight = (r: RightLink) =>
    on.add(r.id).add(`S:${r.src}`).add(`C:${r.channel}`).add(`T:${r.sink}`);
  const [kind, a, b] = f.id.split(':');
  if (f.type === 'link' && kind === 'L') {
    s.left.filter((l) => l.id === f.id).forEach(addLeft);
    s.right.filter((r) => r.src === a && r.channel === b).forEach(addRight);
  } else if (f.type === 'link') {
    const r = s.right.find((x) => x.id === f.id);
    if (r) {
      addRight(r);
      s.left.filter((l) => l.src === r.src && l.channel === r.channel).forEach(addLeft);
    }
  } else if (kind === 'S') {
    s.left.filter((l) => l.src === a).forEach(addLeft);
    s.right.filter((r) => r.src === a).forEach(addRight);
  } else if (kind === 'C') {
    s.left.filter((l) => l.channel === a).forEach(addLeft);
    s.right.filter((r) => r.channel === a).forEach(addRight);
  } else {
    const into = s.right.filter((r) => r.sink === a);
    into.forEach(addRight);
    s.left
      .filter((l) => into.some((r) => r.src === l.src && r.channel === l.channel))
      .forEach(addLeft);
  }
  return on;
}

/** "60% = 3/5", or "100%". */
export function pctExact(f: Frac | null): string {
  if (!f) {
    return '—';
  }
  const e = exact(f);
  return e ? `${fmtPct(f)} = ${e}` : fmtPct(f);
}

/** The label at a ribbon's end. Geometry never changes; only this does. */
export function linkLabel(
  s: Snapshot,
  id: string,
  norm: Norm,
  basis: Basis,
): string | null {
  const l = s.left.find((x) => x.id === id);
  if (l) {
    switch (norm) {
      case 'watts':
        return fmtW(l.w);
      case 'pctSource':
        return pctExact(l.ratio);
      case 'pctSink':
        return pctExact(l.share);
      default: {
        const m = leftMoney(s, l);
        return m?.value ? fmtEur(m.value) : null;
      }
    }
  }
  const r = s.right.find((x) => x.id === id);
  if (!r) {
    return null;
  }
  switch (norm) {
    case 'watts':
      return fmtW(r.w);
    case 'pctSource':
      return pctExact(r.ofSource);
    case 'pctSink':
      return pctExact(r.ofSink);
    default: {
      const m = rightMoney(s, r, basis);
      return m?.value ? fmtEur(m.value) : null;
    }
  }
}

export interface TipRow {
  label: string;
  /** The Home Assistant sensor showing this figure, when it is not the title's. */
  sensor?: string;
  value: string;
  exact?: string | null;
  /** Not a Home Assistant sensor: the chart derived it from stored values. */
  derived?: boolean;
}

export interface Tip {
  title: string;
  on?: string;
  path: string;
  rows: TipRow[];
  note?: string;
}

const wRow = (label: string, w: Frac | null, derived = false): TipRow => ({
  label,
  value: fmtW(w),
  derived,
});
const pRow = (label: string, f: Frac | null, derived = false, sensor?: string): TipRow => ({
  label,
  sensor,
  value: fmtPct(f),
  exact: exact(f),
  derived,
});
const eRow = (label: string, f: Frac | null): TipRow => ({
  label,
  value: fmtEur(f),
  exact: exact(f),
});

export function tipFor(s: Snapshot, f: Focus, basis: Basis): Tip | null {
  if (!f) {
    return null;
  }
  const [kind, a, b] = f.id.split(':');

  if (f.type === 'link' && kind === 'L') {
    const l = s.left.find((x) => x.id === f.id)!;
    const dev = deviceOf(s, l.src);
    const watts = named(s, dev.kind, `source_adapters_${l.channel}_power`, [l.src]);
    const ratio = named(s, dev.kind, `source_adapters_${l.channel}_ratios`, [l.src]);
    const share = named(s, dev.kind, `source_adapters_${l.channel}_shares`, [l.src]);
    const rows = [
      wRow('Watts', l.w),
      pRow(`% of ${l.src}`, l.ratio, false, ratio.sensor ? ratio.name : undefined),
      pRow(
        `% of ${CHANNEL_TITLE[l.channel].toLowerCase()}`,
        l.share,
        false,
        share.sensor ? share.name : undefined,
      ),
    ];
    const m = leftMoney(s, l);
    if (m) {
      rows.push(eRow(m.named.name, m.value));
    }
    return {title: watts.name, on: l.src, path: watts.path, rows};
  }

  if (f.type === 'link') {
    const r = s.right.find((x) => x.id === f.id)!;
    const sink = deviceOf(s, r.sink);
    const rows: TipRow[] = [];
    let title: string;
    let path: string;
    let note: string | undefined;
    if (r.derived) {
      title = `${r.src} → home base load`;
      path = `home_base_load_source_shares[${r.src}] × home_base_load_power`;
      note = 'No sensor: the base load has no meter, so its watts are its stored share times its size.';
      rows.push(wRow('Watts', r.w, true));
    } else if (sink.kind === 'consumer') {
      const p = named(s, 'consumer', 'sink_adapters_source_power', [r.sink, r.src], r.src);
      title = p.name;
      path = p.path;
      rows.push(wRow('Watts', r.w));
    } else if (s.sinks.filter((k) => k.channel === r.channel).length === 1) {
      // The channel's only sink: this ribbon is the source's whole share of
      // the channel, so the source's own channel sensors describe it exactly.
      return tipFor(s, {type: 'link', id: `L:${r.src}:${r.channel}`}, basis);
    } else {
      const p = named(s, sink.kind, 'sink_adapters_source_power', [r.sink, r.src], r.src);
      title = p.sensor ? p.name : `${r.src} → ${r.sink}`;
      path = p.path;
      rows.push(wRow('Watts', r.w));
    }
    rows.push(pRow(`% of ${r.src}`, r.ofSource, true));
    const shareName =
      r.derived || sink.kind === 'grid'
        ? null
        : named(s, sink.kind, 'sink_adapters_source_shares', [r.sink, r.src], r.src);
    rows.push(pRow(`% of ${r.sink}`, r.ofSink, false, shareName?.sensor ? shareName.name : undefined));
    const m = rightMoney(s, r, basis);
    if (m) {
      rows.push(eRow(m.named.name, m.value));
    }
    return {title, on: r.sink === 'home' ? undefined : r.sink, path, rows, note};
  }

  if (kind === 'C') {
    const ch = a as Channel;
    const c = s.channels.find((x) => x.id === ch)!;
    const ratio = named(s, 'combined', `gross_power_${ch}_ratio`);
    const rows = [wRow('Watts', c.w), pRow('Of gross', c.ofGross, false, ratio.sensor ? ratio.name : undefined)];
    const m = channelMoney(s, ch, basis);
    if (m) {
      rows.push(eRow(m.named.name, m.value));
    }
    return {title: CHANNEL_TITLE[ch], on: 'whole home', path: ratio.path, rows};
  }

  const d = deviceOf(s, a ?? b);
  const rows: TipRow[] = [wRow('Reading', d.reading && abs(d.reading))];
  if (d.unexplained.n > 0n) {
    rows.push(wRow('Not explained by the other meters', d.unexplained, true));
  }
  const m = nodeMoney(s, d, basis);
  if (m) {
    rows.push(eRow(m.named.name, m.value));
  }
  const broken = s.broken.filter((x) => x.sink === d.uid);
  return {
    title: d.uid === 'home' ? 'Home base load' : d.uid,
    on: d.role_text,
    path: d.uid === 'home' ? 'home_base_load_power' : `readings[${d.uid}]`,
    rows,
    note: broken.length
      ? `Restriction relaxed: draws ${broken.map((x) => `${fmtW(x.w)} from ${x.src}`).join(', ')}, which its configuration rules out.`
      : undefined,
  };
}

/** "Levelized operating cost rate per sink" → "levelized operating cost". */
const short = (name: string) =>
  name.toLowerCase().replace(/ rate( per \w+)?$/, '').replace(/ per \w+$/, '');

/** A node's headline figure under the current normalization. */
export function nodeLabel(
  s: Snapshot,
  id: string,
  norm: Norm,
  basis: Basis,
): {value: string; caption: string} {
  const [kind, key] = id.split(':');
  if (kind === 'C') {
    const c = s.channels.find((x) => x.id === key)!;
    if (norm === 'eur') {
      const m = channelMoney(s, c.id, basis);
      return {
        value: CHANNEL_TITLE[c.id],
        caption: m ? `${fmtEur(m.value)} · ${short(m.named.name)}` : 'no engine rate',
      };
    }
    const g = c.ofGross;
    const of = !g ? '' : g.d === 1n && g.n === 1n ? ' · all of gross' : ` · ${exact(g) ?? fmtPct(g)} of gross`;
    return {value: CHANNEL_TITLE[c.id], caption: `${fmtW(c.w)}${of}`};
  }
  const d = deviceOf(s, key);
  if (norm === 'eur') {
    const m = nodeMoney(s, d, basis);
    return {
      value: m ? fmtEur(m.value) : '—',
      caption: `${d.uid} — ${m ? short(m.named.name) : d.role_text}`,
    };
  }
  return {
    value: fmtW(d.reading && abs(d.reading)),
    caption: `${d.uid} — ${d.role_text}`,
  };
}

