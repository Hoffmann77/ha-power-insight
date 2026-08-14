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

## Reviewing a pull request's docs

GitHub Pages allows exactly **one** deployment per repository, so a pull request
cannot have its own preview URL without giving up the Actions publishing source
and going back to a `gh-pages` branch. Instead, every PR build attaches the
finished site to the workflow run:

1. Open the PR's **Docs** check → *Summary* → **Artifacts** →
   `docs-site-pr-<number>`.
2. Unpack it over `website/build`.
3. `cd website && npm run serve`.

Use `npm run serve` rather than a generic static server: the site is published
under `/ha-power-insight/`, and a server rooted elsewhere will 404 every asset.

If preview URLs ever become worth the setup, an external host (Cloudflare Pages,
Netlify) is the way to get them — it builds fork PRs in its own sandbox, which
is the part that is genuinely awkward to do safely from this repository.

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
npm run typecheck  # the case-diagram component and the case data
npm run build      # catches broken links and broken heading anchors
```

The build treats broken internal links and broken anchors as **errors**, not
warnings. That is deliberate: the reference-case pages are a specification, and a
link that silently rots undermines the point.

## Markdown vs MDX

`markdown.format` is set to `detect`:

- **`.md`** is parsed as plain CommonMark. Braces and angle brackets in prose
  and code spans are left alone, which is what most pages want.
- **`.mdx`** is parsed as MDX and can import and render React components.

Only pages that actually embed a component — the reference-case pages, and the
landing page — need to be `.mdx`. Prefer `.md` for everything else.

## Versioning

The site publishes **the released docs at the root** and the in-development docs
under `/next`, with a version selector in the navbar.

| Where you edit | Where it appears |
|---|---|
| `docs/` | `/next` — labelled *Next (unreleased)* |
| `website/versioned_docs/version-2026.7/` | the site root — what visitors get by default |

Docusaurus versions by **snapshotting source**, not built output. Cutting a
version copies the whole of `docs/` — markdown, the reference-case JSON, all of it —
into `website/versioned_docs/`, and that copy is then frozen. Day-to-day work
happens in `docs/` and lands under `/next`; nothing you write there changes what
a visitor sees until the next version is cut.

### Cutting a version at release time

```bash
cd website
npm run docusaurus docs:version 2026.8   # MAJOR.MINOR of the release
```

That is the whole ritual. It writes `versioned_docs/version-2026.8/`, a matching
sidebar, and a new entry in `versions.json`; the newest entry becomes what the
root serves. Commit all three.

Old versions stay browsable and are still *rebuilt* on every deploy, because
Docusaurus versions source rather than output — so a theme fix reaches every
version at once.

:::warning[Why reference-case data is passed in as a prop]

That last point cuts both ways. `docs/` is snapshotted; `website/src/` is
**shared across every version**. So the reference-case JSON lives under
`docs/spec/cases/` to be frozen with the prose around it, while the component
that draws it is shared — which is why each page imports its own case data and
passes it in rather than letting the component reach for it.

Break that split and an old version's page will quietly start rendering today's
numbers, which for a page whose entire purpose is pinning down specific values
would be worse than useless.

:::

The MkDocs site was versioned with `mike`. That history stays on the old
`gh-pages` branch and is no longer updated or served.
