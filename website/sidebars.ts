import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// Mirrors the nav the MkDocs site had, plus the reference-case specification.
const sidebars: SidebarsConfig = {
  docs: [
    'index',
    'installation',
    'getting-started',
    {
      type: 'category',
      label: 'Configuration',
      items: [
        'configuration/index',
        'configuration/grid',
        'configuration/pv',
        'configuration/battery',
        'configuration/consumer',
        'configuration/options-and-presets',
      ],
    },
    'entities',
    'concepts',
    'services',
    'faq',
    {
      type: 'category',
      label: 'Reference cases',
      link: {type: 'doc', id: 'spec/index'},
      // Ladder order: each rung adds one device or flips one flag against the
      // rung above it. The last two are the specialists. Keep in step with
      // REFERENCE_CASES in docs/spec/cases/all.ts.
      items: [
        'spec/grid-only',
        'spec/pv-self-consumption',
        'spec/pv-export',
        'spec/metered-load',
        'spec/captive-load',
        'spec/battery-basics',
        'spec/captive-battery',
        'spec/group-captivity',
        'spec/mixed-export-house',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      items: [
        'dev/engine-calculations',
        'dev/source-share-allocation-problem',
        'dev/entity-naming',
        'dev/releasing',
        'dev/options-flow-redesign',
        'dev/case-diagram-handoff',
      ],
    },
  ],
};

export default sidebars;
