# my-design — Skill Catalog

Entry point for choosing which design skill to invoke. All `my-design:*` skills below are vendored into this plugin. The `vercel:*` skills referenced at the bottom remain in their live plugin (auto-updates monthly via `/plugin update vercel`).

## Build / design

| Skill | Use when |
|---|---|
| `my-design:interface-design` | Dashboards, admin panels, SaaS apps. Persists patterns to `.interface-design/system.md` for cross-session consistency. NOT for marketing — redirects there. |
| `my-design:frontend-design` | Production frontend, any context (landing pages, components, pages). Anthropic's official skill. Used by interface-design as the marketing fallback. |
| `my-design:design-taste-frontend` | Stricter alternative to frontend-design — opinionated on RSC patterns, Tailwind v3/v4, Phosphor/Radix icons, three-axis dials (variance / motion / density). Try when frontend-design feels too permissive. |
| `my-design:frontend-design-pro` | Greenfield style exploration. 11 distinct aesthetics (Swiss, Glassmorphism, Brutalism, Cyberpunk, etc.) with complete specs. |
| `my-design:ui-ux-pro-max` | Generate a complete design system from product description. CLI-driven (Python). Run once per new project to produce `design-system/MASTER.md`. |

## Audit / review

| Skill | Use when |
|---|---|
| `my-design:ui-refactor` | "This UI looks off" — visual hierarchy, spacing, shadow audit (Refactoring UI methodology by Wathan/Schoger). |
| `my-design:ux-heuristics` | Usability audit. Nielsen's 10 heuristics + Krug's "Don't Make Me Think". Returns severity-scored issues. |

## Brand / theming

| Skill | Use when |
|---|---|
| `my-design:brand-guidelines` | Output needs to match a defined brand identity (colors, fonts, tone). |
| `my-design:theme-factory` | Quick theming of slides, docs, or HTML — 10 ready-made themes with palettes and font pairings. |

## Meta

| Skill | Use when |
|---|---|
| `my-design:skill-creator` | Adding or editing a SKILL.md inside this plugin. |

## Live (not vendored — kept in `vercel` plugin)

These stay in `~/.claude/plugins/cache/claude-plugins-official/vercel/` and auto-update. Vercel is the only design-adjacent plugin shipping monthly updates, so vendoring would just create maintenance pain.

| Skill | Use when |
|---|---|
| `vercel:react-best-practices` | React TSX code-quality review. Triggers automatically on multi-component edits. |
| `vercel:shadcn` | shadcn/ui composition patterns, theming, custom registries. |
| `vercel:nextjs` | Next.js App Router — RSC, Server Actions, routing, middleware, caching. |
| `vercel:turbopack` | Next.js bundler config and HMR debugging. |

(Other `vercel:*` skills handle deployment / infra and aren't design-relevant. See `/plugin` for the full list.)

## Update workflow

- **Vendored skills**: re-copy from upstream when you want fresh content, then `/plugin update kasey-plugins`.
  - Cloned-source skills (5): re-pull from `~/dev_wsl/skill-review/` and re-`cp -r` into `skills/`.
  - Anthropic-installed skills (4): re-`cp -r` from `~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/`.
  - ui-ux-pro-max: re-`cp -r` from `~/.claude/plugins/cache/ui-ux-pro-max-skill/...`.
- **`vercel:*` skills**: `/plugin update vercel`.

## Migration notes

These originals remain installed alongside their vendored copies. Mute them in `/plugin` after you've verified the `my-design:*` versions work, otherwise both load into context simultaneously:

- `document-skills:frontend-design` → vendored as `my-design:frontend-design`
- `document-skills:theme-factory` → vendored as `my-design:theme-factory`
- `document-skills:brand-guidelines` → vendored as `my-design:brand-guidelines`
- `document-skills:skill-creator` → vendored as `my-design:skill-creator`
- `ui-ux-pro-max:ui-ux-pro-max` → vendored as `my-design:ui-ux-pro-max`
