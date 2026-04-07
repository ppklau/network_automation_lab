# Site Maintenance Guide

This document records what was built, why decisions were made, and how to keep the site up to date as the lab evolves.

---

## What was built

### The problem being solved

The lab is an open-source network automation guide. A static documentation site was needed that:

- Provides an interactive, navigable view of the network architecture with clickable diagrams
- Acts as a polished public face for the project alongside the Network Automation Handbook
- Gives readers a better experience than raw Markdown on GitHub

### Technology choices

**Framework: Starlight (Astro)**

Starlight was chosen over VitePress (Vue) and mdBook (Rust) for three reasons:

1. *Visual polish out of the box.* Starlight's default theme — dark/light mode, sidebar navigation, search, hero landing page — looks professional without custom design work.
2. *MDX support.* Pages can mix Markdown content with Astro components. This is what makes the Mermaid diagram components possible without fighting the framework.
3. *Astro's island architecture.* Interactive components (Mermaid rendering) can be dropped into static Markdown pages without making the entire site a client-side SPA.

**Mermaid diagrams: client-side rendering via a custom component**

The initial approach was `rehype-mermaid`, which renders Mermaid to SVG at build time. This was abandoned because it requires full Playwright/Chromium browser binaries (~300MB) as a build dependency. The alternative is a small `Mermaid.astro` component that:

- Renders diagrams in the browser using the `mermaid` npm package
- Detects Starlight's `data-theme` attribute on `<html>` and re-renders with the correct Mermaid theme when the user toggles dark/light mode
- Uses `astro:page-load` (not `DOMContentLoaded`) so it works correctly with Astro's view transitions

The downside is that diagrams are not visible if JavaScript is disabled. Acceptable trade-off for a technical audience.

**Hosting: GitHub Pages via GitHub Actions**

The repo is public so GitHub Pages is free. A GitHub Actions workflow (`.github/workflows/deploy-site.yml` at the repo root) builds the Astro site on every push to `main` that touches `site/**` and deploys to GitHub Pages automatically.

---

## Repository structure

```
network_automation_lab/
  site/                          ← this directory (Astro/Starlight site)
    src/
      content/
        docs/                    ← source of truth for all guide content
          preface.md
          part1/ … part9/
          appendix/
          architecture/          ← site-only pages (Mermaid diagrams, not in lab)
          index.mdx              ← site landing page
      assets/                    ← logos and static assets
      components/                ← Mermaid.astro and other custom components
      styles/                    ← custom CSS
    public/                      ← images and other static files served as-is
    astro.config.mjs
    package.json
  playbooks/                     ← lab code (MIT licensed)
  scripts/
  templates/
  … (other lab directories)
```

`site/src/content/docs/` is the **single source of truth** for all guide prose. There is no separate guide directory — edit content here directly.

---

## How content is structured

### Page anatomy

Every guide chapter file follows this pattern:

```markdown
---
title: "Chapter N: The Chapter Title"
---

[chapter content]
```

The frontmatter `title` field is what Starlight uses for the sidebar label, browser tab title, and page `<h1>`.

### Architecture pages

Architecture pages are `.mdx` files that import the `Mermaid.astro` component:

```mdx
import Mermaid from '../../../components/Mermaid.astro';

<Mermaid code={`
graph TB
  ...
`} />
```

Clickable nodes use Mermaid's `click` directive:

```
click NODE_ID href "/target-slug/" "Tooltip text"
```

---

## Sidebar configuration

The sidebar is defined entirely in `astro.config.mjs`. It does not autogenerate from the file system — ordering and labelling are explicit.

Every new chapter or section must be added to the sidebar manually:

```js
{
  label: 'Part N — Part Title',
  items: [
    { label: 'Chapter Title', slug: 'partN/NN-filename' },
  ],
}
```

The `slug` value must match the file path under `src/content/docs/`, without the `.md` extension and without a leading slash.

---

## How to update content

### Editing an existing chapter

Edit the file directly in `site/src/content/docs/partN/NN-filename.md`. Commit and push to `main` — the Actions workflow redeploys the site automatically.

### Adding a new chapter

1. Create the file in `site/src/content/docs/partN/NN-filename.md` with frontmatter:
   ```markdown
   ---
   title: "Chapter N: The Chapter Title"
   ---
   ```
2. Add an entry to the sidebar in `astro.config.mjs`:
   ```js
   { label: 'Chapter Title', slug: 'partN/NN-filename' }
   ```
3. Run `npm run dev` locally to verify the page renders and appears in the sidebar.
4. Commit and push.

### Adding a new part

1. Create the directory: `site/src/content/docs/partN/`
2. Add chapter files with frontmatter (as above).
3. Add a new sidebar group to `astro.config.mjs`.
4. Verify with `npm run build`, commit and push.

### Updating network topology diagrams

The architecture pages contain hand-authored Mermaid diagrams. They do not auto-derive from the SoT. When the topology changes, update the diagrams manually:

- **Global overview:** `src/content/docs/architecture/index.mdx`
- **EMEA detail:** `src/content/docs/architecture/emea.mdx`
- **Americas detail:** `src/content/docs/architecture/americas.mdx`
- **APAC detail:** `src/content/docs/architecture/apac.mdx`
- **Frankfurt detail:** `src/content/docs/architecture/frankfurt.mdx`

Each page also contains prose tables (device inventory, IPAM, BGP ASNs). Update those to match. Test locally with `npm run dev` — Mermaid renders in the browser, so errors appear in the browser console rather than the build output.

### Updating Grafana dashboard screenshots

Screenshots live in `public/images/`. Replace the image file keeping the same filename. If the filename changes, update the reference in the Markdown file:

```markdown
![BGP session overview](/images/grafana-bgp-overview.png)
```

---

## Local development

```bash
cd site
npm install
npm run dev      # dev server at http://localhost:4321
npm run build    # production build to site/dist/
npm run preview  # preview the production build locally
```

---

## Known issues and deferred work

| Issue | Impact | Fix |
|-------|--------|-----|
| Duplicate `# Heading` on chapter pages | Minor — two headings visible | Remove the `# ` line from each chapter file |
| `jinja2` / `cron` not syntax-highlighted | Minor — falls back to plaintext | Add custom language definitions in `astro.config.mjs` via `expressiveCode.langs` |
| Mermaid chunk size warning at build | None — just a Vite warning | Split the Mermaid import dynamically if bundle size becomes a concern |
| No `site` URL in `astro.config.mjs` | Sitemap not generated | Add `site: 'https://ppklau.github.io/network_automation_lab'` once confirmed |
| Placeholder SVG logos | Brand | Replace `src/assets/logo-light.svg` and `logo-dark.svg` with a proper logo |
| No Grafana screenshots | Gap in Ch.26 | Take screenshots at exercise completion and add to `public/images/` |
