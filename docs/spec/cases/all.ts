/**
 * Every reference case, in index order.
 *
 * This barrel lives inside `docs/` on purpose: the case data is part of the
 * documentation and must be snapshotted with it when a docs version is cut.
 * The component that renders it lives in `website/src/` and is shared across
 * versions, so pages pass the data in rather than letting the component reach
 * for it. The property catalog travels the same way and for the same reason.
 */
import BASELINE_MIX from './baseline-mix.json';
import CAPTIVE_BATTERY from './captive-battery.json';
import GROUP_CAPTIVITY from './group-captivity.json';
import GRID_EXPORT from './grid-export.json';
import CATALOG from '../properties.json';

import type {
  PropertyCatalog,
  ReferenceCase,
} from '@site/src/components/CaseDiagram/types';

export const REFERENCE_CASES = [
  BASELINE_MIX,
  CAPTIVE_BATTERY,
  GROUP_CAPTIVITY,
  GRID_EXPORT,
] as unknown as ReferenceCase[];

/** What each published property means, its unit, and the layer it belongs to. */
export const PROPERTIES = CATALOG as unknown as PropertyCatalog;

export function referenceCase(id: string): ReferenceCase {
  const found = REFERENCE_CASES.find((c) => c.id === id);
  if (!found) {
    throw new Error(`unknown reference case ${id}`);
  }
  return found;
}

export default REFERENCE_CASES;
