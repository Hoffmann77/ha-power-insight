import MDXComponents from '@theme-original/MDXComponents';
import CaseDiagram from '@site/src/components/CaseDiagram';

// Registered globally so a reference-case page only imports its data, never the
// component. Keeps the case JSON — which versions with the docs — the only
// thing a page has to name.
export default {
  ...MDXComponents,
  CaseDiagram,
};
