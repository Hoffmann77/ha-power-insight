/**
 * Every anchor case, in index order.
 *
 * This barrel lives inside `docs/` on purpose: the case data is part of the
 * documentation and must be snapshotted with it when a docs version is cut.
 * The component that renders it lives in `website/src/` and is shared across
 * versions, so pages pass the data in rather than letting the component reach
 * for it.
 */
import A001 from './A-001.json';
import A002 from './A-002.json';
import A003 from './A-003.json';
import A004 from './A-004.json';

import type {AnchorCase} from '@site/src/components/AnchorDiagram/types';

export const ANCHOR_CASES = [A001, A002, A003, A004] as unknown as AnchorCase[];

export function anchorCase(id: string): AnchorCase {
  const found = ANCHOR_CASES.find((c) => c.id === id);
  if (!found) {
    throw new Error(`unknown anchor case ${id}`);
  }
  return found;
}

export default ANCHOR_CASES;
