import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// The markdown lives at the repository root in `docs/`, not inside this
// directory: contributors edit prose next to the code it documents, and this
// folder holds only the site machinery. Everything below is wired around that.

// The published site carries the released versions only. The deploy build sets
// DOCS_RELEASED_ONLY=true; everywhere else (`npm start`, pull-request builds)
// `docs/` is built too, under /next, so it can be read and its links checked
// before it is ever released.
const releasedOnly = process.env.DOCS_RELEASED_ONLY === 'true';

const config: Config = {
  title: 'Power Insight',
  tagline:
    'Real-time electricity cost, savings, and power-distribution insights for ' +
    'Home Assistant — grid, solar, batteries, and consumers in one place.',
  favicon: 'img/favicon.png',

  url: 'https://hoffmann77.github.io',
  baseUrl: '/ha-power-insight/',
  organizationName: 'Hoffmann77',
  projectName: 'ha-power-insight',
  trailingSlash: false,

  // A broken link is a broken promise in a spec site — fail the build.
  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',

  i18n: {defaultLocale: 'en', locales: ['en']},

  // `detect` keeps `.md` on CommonMark and reserves MDX for `.mdx`. The prose
  // migrated from MkDocs is full of `{...}` and `<...>` inside code spans that
  // MDX would try to evaluate; only the pages that actually embed a component
  // opt in.
  markdown: {
    format: 'detect',
    hooks: {onBrokenMarkdownLinks: 'throw'},
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/Hoffmann77/ha-power-insight/edit/main/docs/',
          showLastUpdateTime: true,
          // Visitors get the released versions. `docs/` is the unreleased
          // version: never published, only built for previews and checks. A
          // release turns it into a version (see docs/dev/releasing.md).
          includeCurrentVersion: !releasedOnly,
          ...(releasedOnly
            ? {}
            : {versions: {current: {label: 'Next (unreleased)', path: 'next'}}}),
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],

  // MkDocs Material shipped search built in; Docusaurus does not. This is the
  // offline equivalent — indexed at build time, no external service, so the
  // site keeps working with no network.
  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexBlog: false,
        docsDir: '../docs',
        docsRouteBasePath: '/',
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  themeConfig: {
    image: 'img/logo.png',
    colorMode: {respectPrefersColorScheme: true},
    navbar: {
      // No logo image here: brand/logo.png is a wordmark, so it duplicated the
      // title, and being dark-on-transparent it vanished in dark mode. Add it
      // back with a `srcDark` variant once one exists.
      title: 'Power Insight',
      items: [
        {type: 'docSidebar', sidebarId: 'docs', position: 'left', label: 'Docs'},
        // `doc` items resolve inside the version being viewed. Both pages exist
        // in every version; a `docSidebar` item for the developer docs would
        // not, since 2026.7 predates the `dev` sidebar.
        {type: 'doc', docId: 'spec/index', label: 'Reference cases', position: 'left'},
        {type: 'doc', docId: 'dev/engine-calculations', label: 'Developers', position: 'left'},
        {type: 'docsVersionDropdown', position: 'right'},
        {
          href: 'https://github.com/Hoffmann77/ha-power-insight',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Installation', to: '/installation'},
            {label: 'Getting started', to: '/getting-started'},
          ],
        },
        {
          // Footer links point at the latest release, so only pages every
          // version has belong here; the sidebar has the rest.
          title: 'Reference',
          items: [
            {label: 'Reference cases', to: '/spec'},
            {label: 'Engine decisions', to: '/dev/engine-calculations'},
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/Hoffmann77/ha-power-insight',
            },
            {
              label: 'Issues',
              href: 'https://github.com/Hoffmann77/ha-power-insight/issues',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Hoffmann77 — MIT License`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'yaml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
