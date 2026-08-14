/**
 * The engine's four layers, as the property catalog defines them.
 *
 * The tab row and the value table are driven by the same list, so a property
 * can never appear under one heading in the graph and another in the table.
 * Short labels are for the tab; the catalog's own wording is the section
 * heading, because that is the vocabulary the rest of the spec uses.
 */
import type {Expectation, LayerId, PropertyCatalog} from './types';

export const LAYERS: {id: LayerId; short: string; fallback: string}[] = [
  {id: '1', short: 'Totals', fallback: 'Readings and totals'},
  {id: '2', short: 'Provenance', fallback: 'Source provenance'},
  {
    id: '3',
    short: 'Channels',
    fallback: 'Channel split and per-source attribution',
  },
  {id: '4', short: 'Money', fallback: 'The monetary model'},
];

/** What this layer is called on the page. */
export function layerTitle(
  id: LayerId,
  catalog: PropertyCatalog | undefined,
): string {
  const layer = LAYERS.find((l) => l.id === id);
  return catalog?.layers?.[id] ?? layer?.fallback ?? `Layer ${id}`;
}

/**
 * A state's expectations, bucketed by layer.
 *
 * A property the catalog does not document still has to be shown — silently
 * dropping a published value would be the one failure mode this table exists to
 * prevent — so it falls into layer 1 alongside the readings.
 */
export function groupByLayer(
  expectations: Expectation[],
  catalog: PropertyCatalog | undefined,
): {[k in LayerId]: Expectation[]} {
  const out: {[k in LayerId]: Expectation[]} = {'1': [], '2': [], '3': [], '4': []};
  for (const e of expectations) {
    const layer = String(catalog?.properties?.[e.property]?.layer ?? 1) as LayerId;
    (out[layer] ?? out['1']).push(e);
  }
  return out;
}
