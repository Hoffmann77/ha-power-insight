/**
 * Every reference case, in ladder order.
 *
 * The order is the corpus's argument, not an accident: each case is the
 * smallest wiring that can express the decision it settles, and every entry
 * adds one device or flips one configuration flag against the entry above it.
 * The last two are specialists — they are allowed to be large because the
 * decisions they carry cannot be shown in anything smaller.
 *
 * This barrel lives inside `docs/` on purpose: the case data is part of the
 * documentation and must be snapshotted with it when a docs version is cut.
 * The component that renders it lives in `website/src/` and is shared across
 * versions, so pages pass the data in rather than letting the component reach
 * for it. The property catalog and the coverage table travel the same way and
 * for the same reason.
 */
import GRID_ONLY from './grid-only.json';
import PV_SELF_CONSUMPTION from './pv-self-consumption.json';
import PV_EXPORT from './pv-export.json';
import METERED_LOAD from './metered-load.json';
import CAPTIVE_LOAD from './captive-load.json';
import BATTERY_BASICS from './battery-basics.json';
import CAPTIVE_BATTERY from './captive-battery.json';
import GROUP_CAPTIVITY from './group-captivity.json';
import MIXED_EXPORT_HOUSE from './mixed-export-house.json';
import CATALOG from '../properties.json';
import COVERAGE from './coverage.json';

import type {
  Coverage,
  PropertyCatalog,
  ReferenceCase,
} from '@site/src/components/CaseDiagram/types';

export const REFERENCE_CASES = [
  GRID_ONLY,
  PV_SELF_CONSUMPTION,
  PV_EXPORT,
  METERED_LOAD,
  CAPTIVE_LOAD,
  BATTERY_BASICS,
  CAPTIVE_BATTERY,
  GROUP_CAPTIVITY,
  MIXED_EXPORT_HOUSE,
] as unknown as ReferenceCase[];

/** What each published property means, its unit, and the layer it belongs to. */
export const PROPERTIES = CATALOG as unknown as PropertyCatalog;

/**
 * Which rungs each property is actually settled by, and which decision each
 * case carries. Generated with the cases, so it cannot drift from them.
 */
export const COVERAGE_TABLE = COVERAGE as unknown as Coverage;

export function referenceCase(id: string): ReferenceCase {
  const found = REFERENCE_CASES.find((c) => c.id === id);
  if (!found) {
    throw new Error(`unknown reference case ${id}`);
  }
  return found;
}

export default REFERENCE_CASES;
