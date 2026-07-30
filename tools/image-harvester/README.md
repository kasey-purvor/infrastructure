# image-harvester

Harvest all images from an Instagram profile via the [ScrapFly](https://scrapfly.io) web-scraping API,
saved to disk with a metadata manifest.

> Scope: **Instagram only.** Logged-out, public profiles. Images only (videos skipped).

## Install

```bash
cd tools/image-harvester
uv venv && uv pip install -e ".[dev]"
```

## Use

```bash
export SCRAPFLY_KEY=scp-live-xxxxxxxx

# newest 12 posts of a profile -> ./output/madtev/
image-harvester madtev

# whole profile (paginates; asks to confirm first)
image-harvester madtev --all

# preview only: enumerate + report counts + estimated credits, download nothing
image-harvester madtev --all --dry-run

# a full profile URL works too
image-harvester https://www.instagram.com/madtev/ --limit 50 --concurrency 8
```

### Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `username` (positional) | — | IG username or profile URL |
| `--limit N` | `12` | Max posts (one page = no GraphQL pagination) |
| `--all` | off | Paginate the entire profile (overrides `--limit`) |
| `--output DIR` | `./output` | Output root (`DIR/<username>/`) |
| `--concurrency N` | `6` | Parallel image downloads |
| `--page-delay SECS` | `2.0` | Polite pause between feed pages during `--all` (0 disables) |
| `--dry-run` | off | Enumerate + report, download nothing |
| `--yes` | off | Skip the `--all` confirmation prompt |
| `--api-key KEY` | `$SCRAPFLY_KEY` | ScrapFly API key override |

## Output

```
output/madtev/
├── manifest.jsonl                       # one JSON object per post
├── 2023-09-16_CxQwZ0gOIFp_01.jpg
├── 2023-09-16_CxQwZ0gOIFp_02.jpg
└── ...
```

Re-running is **idempotent**: every run re-enumerates (fresh, non-expired image URLs) and only
downloads images whose file isn't already on disk — so it resumes interrupted runs and pulls only
new posts on later runs.

## Develop

```bash
uv run --extra dev pytest
```

See `CLAUDE.md` for the full design, decisions, and module map.
