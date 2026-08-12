import MDXComponents from '@theme-original/MDXComponents';
import AnchorDiagram from '@site/src/components/AnchorDiagram';

// Registered globally so an anchor page only imports its data, never the
// component. Keeps the case JSON — which versions with the docs — the only
// thing a page has to name.
export default {
  ...MDXComponents,
  AnchorDiagram,
};
