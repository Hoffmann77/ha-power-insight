# Docs versioning & release process

The documentation site is **versioned** with
[`mike`](https://github.com/jimporter/mike). `mike` builds each version of the
site into its own subdirectory of the `gh-pages` branch, maintains a
`versions.json`, and renders the version selector in the site header.

## How versions are published

Everything is driven by the [`docs.yaml`](https://github.com/Hoffmann77/ha-power-insight/blob/main/.github/workflows/docs.yaml)
workflow:

| Trigger | What gets deployed |
|---|---|
| Push to `main` | The **`dev`** version — in-development docs for the next release. |
| Push a release tag (e.g. `0.1.0-beta.3`) | A version named after the tag's **`MAJOR.MINOR`** (e.g. `0.1`), with the **`latest`** alias moved onto it and made the site default. |
| Manual *Run workflow* | Whatever `version` / `alias` you enter (escape hatch). |

The site root always redirects to a real version: `latest` once a release
exists, otherwise `dev`.

!!! info "Grouping by MAJOR.MINOR"
    Patch and beta releases within a minor series (e.g. `0.1.0-beta.1`,
    `0.1.0-beta.2`, `0.1.0`) all publish to the same `0.1` version, so the
    selector stays short. When `0.2` or `1.0` ships, `latest` moves to it and
    the older series stays browsable.

## Cutting a release

1. Merge all doc changes for the release into `main` (they land under `dev`).
2. Tag the release and push the tag:

    ```bash
    git tag 0.1.0-beta.4
    git push origin 0.1.0-beta.4
    ```

3. The workflow deploys `0.1` + `latest` and sets it as the default. Done.

## Deploying manually

From **Actions → Docs → Run workflow**, or locally with a push:

```bash
pip install -r docs/requirements.txt

# Deploy/refresh a version and alias:
mike deploy --push --update-aliases 0.1 latest

# Choose what the site root points at:
mike set-default --push latest

# Inspect / remove versions:
mike list
mike delete --push <version>
```

## GitHub Pages setup (one-time)

Because `mike` owns the `gh-pages` branch, Pages must serve **from that
branch**:

**Settings → Pages → Build and deployment → Source: _Deploy from a branch_ →
Branch: `gh-pages` / `/ (root)`**.

The workflow only needs `contents: write` permission (to push to `gh-pages`);
it does not use the "GitHub Actions" Pages source.
