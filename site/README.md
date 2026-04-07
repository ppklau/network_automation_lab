# ACME Investments — Network Automation Lab Site

Companion documentation site for the ACME Investments Network Automation Lab guide. Built with [Starlight](https://starlight.astro.build/) (Astro).

## Commands

Run from the root of this directory:

| Command           | Action                                      |
|:------------------|:--------------------------------------------|
| `npm install`     | Install dependencies                        |
| `npm run dev`     | Start dev server at `http://localhost:4321` |
| `npm run build`   | Build production site to `./dist/`          |
| `npm run preview` | Preview the production build locally        |

## Structure

```
src/
  assets/               # Logo SVGs and images
  components/
    Mermaid.astro       # Client-side Mermaid diagram renderer
  content/
    docs/
      index.mdx         # Landing page (splash hero)
      preface.md
      architecture/     # Network diagram drill-down pages
      part1/ … part9/   # Guide chapters (imported from lab repo)
      appendix/
  styles/
    custom.css          # Brand colours and component overrides
astro.config.mjs        # Sidebar structure, site metadata
```

## Updating the site

See [MAINTENANCE.md](./MAINTENANCE.md) for a full guide on keeping the site in sync with the lab repo, adding new chapters, and updating architecture diagrams.
