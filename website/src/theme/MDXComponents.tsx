import MDXComponents from '@theme-original/MDXComponents';
import FlowSankey from '@site/src/components/FlowSankey';
import {ButtonLink, Card, CardGrid} from '@site/src/components/Cards';

// Registered globally so a reference-case page only imports its data, never the
// component. Keeps the case JSON — which versions with the docs — the only
// thing a page has to name.
export default {
  ...MDXComponents,
  FlowSankey,
  ButtonLink,
  Card,
  CardGrid,
};
