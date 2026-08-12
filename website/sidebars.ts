import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// Mirrors the nav the MkDocs site had, plus the anchor-case specification.
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
      label: 'Anchor cases',
      link: {type: 'doc', id: 'spec/index'},
      items: ['spec/a-001', 'spec/a-002', 'spec/a-003', 'spec/a-004'],
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
        'dev/anchor-diagram-handoff',
      ],
    },
  ],
};

export default sidebars;
