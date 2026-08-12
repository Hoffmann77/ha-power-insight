# Docs publishing

The documentation site is a [Docusaurus](https://docusaurus.io/) site. The
prose lives at the repository root in `docs/`, next to the code it documents;
`website/` holds only the site machinery (config, React components, styles), so
the Python project root stays free of Node tooling.

## How it is published

Everything is driven by the [`docs.yaml`](https://github.com/Hoffmann77/ha-power-insight/blob/main/.github/workflows/docs.yaml)
workflow:

| Trigger | What happens |
|---|---|
| Pull request touching `docs/` or `website/` | Type-check and build only — a broken link or a bad MDX page fails the PR. |
| Push to `main` | Build and publish to GitHub Pages. |
| Manual *Run workflow* | Same as a push to `main`. |

Publishing uses the **GitHub Actions Pages source**, so there is no `gh-pages`
branch and no bot commits in the history. The artifact the build produces is
handed straight to `actions/deploy-pages`.

:::info[One-time Pages setting]

**Settings → Pages → Build and deployment → Source: _GitHub Actions_.**

This replaced the old *Deploy from a branch → `gh-pages`* setting, which the
previous MkDocs + `mike` setup required.

:::

## Working on the docs locally

```bash
cd website
npm install
npm start          # dev server with hot reload on http://localhost:3000
```

Two checks worth running before pushing, because CI runs both:

```bash
npm run typecheck  # the anchor-diagram component and the case data
npm run build      # catches broken links and broken heading anchors
```

The build treats broken internal links and broken anchors as **errors**, not
warnings. That is deliberate: the anchor-case pages are a specification, and a
link that silently rots undermines the point.

## Markdown vs MDX

`markdown.format` is set to `detect`:

- **`.md`** is parsed as plain CommonMark. Braces and angle brackets in prose
  and code spans are left alone, which is what most pages want.
- **`.mdx`** is parsed as MDX and can import and render React components.

Only pages that actually embed a component — the anchor-case pages, and the
landing page — need to be `.mdx`. Prefer `.md` for everything else.

## Versioning

The site currently publishes a **single version**. The MkDocs site was versioned
with `mike`; that history stays browsable on the old `gh-pages` branch but is no
longer updated.

Docusaurus versions by snapshotting: `npm run docusaurus docs:version 1.0` copies
the current `docs/` into `website/versioned_docs/version-1.0/`. Worth turning on
when the integration hits 1.0 and the docs need to describe more than one
supported release — before that it mostly adds ceremony.

:::warning[If you do enable versioning]

The anchor-case JSON lives under `docs/spec/anchors/` precisely so it gets
snapshotted with the prose. The component that renders it lives in
`website/src/` and is **shared across all versions**, which is why every page
passes its case data in as a prop rather than letting the component import it.
Keep that split, or an old version's page will start rendering with today's
data.

:::
