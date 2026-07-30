# scrapfly-mcp

Two local [MCP](https://modelcontextprotocol.io) servers over the official `scrapfly-sdk`:

- **scrapfly-scrape** — `fetch_page`, `account_info`, `take_screenshot` (synchronous).
- **scrapfly-crawl** — `start_crawl`, `crawl_status`, `crawl_contents`, `list_crawled_urls`, `cancel_crawl` (async job lifecycle; the agent polls `crawl_status`, the servers never block).

## Layout

A npm-workspaces monorepo:

```
packages/core           shared client factory, key loading, error mapping, MCP helpers
packages/scrape-server  the scrapfly-scrape MCP server
packages/crawl-server   the scrapfly-crawl MCP server
```

## Setup

```bash
npm install
npm run build          # tsc -b (core -> servers, in dependency order)
npm test               # vitest across all packages (build core first)
```

Set `SCRAPFLY_API_KEY` in the environment that launches each server (injected via the MCP client's `env` block — see the servers registered with `claude mcp add`).

See `docs/specs/` and `docs/plans/` for the design and the implementation plan.
