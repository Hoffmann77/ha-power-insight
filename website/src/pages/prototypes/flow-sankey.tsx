import React from 'react';
import Layout from '@theme/Layout';
import Head from '@docusaurus/Head';

import FlowSankey from '@site/src/components/FlowSankey';
import CaseDiagram from '@site/src/components/CaseDiagram';
import MIXED_EXPORT_HOUSE from '@site/../docs/spec/cases/mixed-export-house.json';
import CATALOG from '@site/../docs/spec/properties.json';
import type {PropertyCatalog, ReferenceCase} from '@site/src/components/CaseDiagram/types';

const CASE = MIXED_EXPORT_HOUSE as unknown as ReferenceCase;
const PROPERTIES = CATALOG as unknown as PropertyCatalog;

/**
 * PROTOTYPE page — a standalone page under `src/pages/`, so it is not part of
 * any versioned docs and not in the sidebar. It renders the Sankey against
 * `mixed-export-house`, with the current diagram underneath for comparison.
 */
export default function FlowSankeyPrototype(): React.ReactElement {
  return (
    <Layout title="Sankey prototype" description="Prototype of a Sankey flow diagram">
      <Head>
        <meta name="robots" content="noindex" />
      </Head>
      <main className="container margin-vert--lg">
        <h1>Sankey prototype: {CASE.title}</h1>
        <p>
          A three-column take on the reference-case diagram. Sources on the left
          feed the four <b>channels</b> gross power splits into, and the channels
          feed the sinks. Each link into a channel is one set of per-source sensors
          ("Production to home consumption", its ratio and its share). Each ribbon
          out of a channel keeps its source's colour, so a sink's bundle of
          ribbons shows where its power came from.
        </p>
        <FlowSankey case={CASE} properties={PROPERTIES} />

        <h2 className="margin-top--xl">The current diagram, for comparison</h2>
        <CaseDiagram case={CASE} properties={PROPERTIES} />
      </main>
    </Layout>
  );
}
