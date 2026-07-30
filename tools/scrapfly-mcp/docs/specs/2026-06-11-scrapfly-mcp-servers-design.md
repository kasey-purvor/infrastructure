# Scrapfly MCP Servers — Design

- **Date:** 2026-06-11
- **Status:** Approved design, pending spec review → implementation plan
- **Author:** Kasey
- **Location (final home):** `infrastructure/tools/scrapfly-mcp/`

## 1. Summary

Build two local [Model Context Protocol (MCP)](https://modelcontextprotocol.io) servers that give Claude Code first-class access to Scrapfly, with the **web scraper** and the **crawler** kept as separate servers so each has one coherent mental model. Both are thin TypeScript layers over the official [`scrapfly-sdk`](https://www.npmjs.com/package/scrapfly-sdk) (with a REST fallback for the crawler if the SDK does not expose it). Every Scrapfly option is surfaced as a documented tool parameter — "options clearly explained" is a primary requirement, not an afterthought.

This replaces the previously-configured **hosted** Scrapfly MCP (`scrapfly-cloud-mcp` → `https://mcp.scrapfly.io/mcp`), which fell out of the active config during a `CLAUDE_CONFIG_DIR` migration. The hosted entry will **not** be restored.

## 2. Goals / Non-goals

### Goals
- Two independent-but-shared-core local MCP servers: `scrapfly-scrape` (synchronous) and `scrapfly-crawl` (asynchronous job lifecycle).
- Expose Scrapfly options as fully-documented, typed tool parameters.
- Reuse the option set and error/retry lessons already encoded in `ypo_scraper/scrapfly/` (`scrape_client.py`, `crawler_client.py`, `config.py`).
- Keep the API key out of source and out of the future git repo (env-var injection at registration).
- Fit cleanly inside the future single `infrastructure` repo (workspace scoped to `scrapfly-mcp/`).

### Non-goals
- No blocking/long-running tools (no port of the Python `poll()` loop — see §6).
- No extraction/AI-parsing tools, no monitoring API, no cloud-browser tools in v1.
- Not re-registering the hosted `scrapfly-cloud-mcp` server.
- The git-repo consolidation of `infrastructure/` is tracked separately as the final step, not part of this build.

## 3. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Language/stack | **TypeScript** + `@modelcontextprotocol/sdk` | User preference; matches majority of existing `mcp-*` folders. |
| Scrapfly access | Official `scrapfly-sdk` (TS), REST fallback for crawler | Typed configs; mirrors the Python SDK shape. Crawler-in-SDK to be verified at build (§9). |
| Structure | **Shared-core monorepo** (npm workspaces) | One `core` package + two server packages; DRY for client/error/retry. |
| Naming | **verb form** | Folders `scrape-server`/`crawl-server`; servers `scrapfly-scrape`/`scrapfly-crawl`; tools e.g. `mcp__scrapfly-scrape__fetch_page`. |
| Scrape server tools | `fetch_page` + `account_info` + `take_screenshot` | Fuller scrape surface; account check is a free pre-flight before big crawls. |
| Hosted entry | **Retire** | Local pair fully replaces it; remove stale `mcp__scrapfly-cloud-mcp__*` allow-rule. |
| API key | `SCRAPFLY_API_KEY` env var | Existing convention in `config.py`; injected via `.claude.json` `env` block. |
| Transport | stdio | Local servers launched by Claude Code as child processes. |

## 4. Architecture

```
infrastructure/tools/scrapfly-mcp/
  package.json            # workspaces root (private), no app code
  tsconfig.base.json
  docs/specs/             # this document
  packages/
    core/                 # shared library (not an MCP server)
      src/
        client.ts         # createClient(): reads SCRAPFLY_API_KEY, returns ScrapflyClient
        errors.ts         # ScrapflyError/HTTP -> structured MCP tool error (keeps is_retryable, credits)
        retry.ts          # 429 backoff helper (from crawler_client.py)
        schemas.ts        # shared zod fragments: asp, country, cache, cache_ttl
        index.ts
    scrape-server/        # registered as  scrapfly-scrape   (synchronous)
      src/index.ts        # tools: fetch_page, account_info, take_screenshot
    crawl-server/         # registered as  scrapfly-crawl    (async lifecycle)
      src/index.ts        # tools: start_crawl, crawl_status, crawl_contents, list_crawled_urls, cancel_crawl
```

### Data flow (both servers)
1. Claude calls a tool with typed args.
2. Server validates args via zod, maps them to a Scrapfly config/REST body.
3. `core.createClient()` (or a retrying REST call) executes against Scrapfly.
4. Errors pass through `core.errors` → a clean tool error including credits used and whether a retry is sensible.
5. The server distills the Scrapfly response to a compact, model-friendly result.

## 5. Scrape server — `scrapfly-scrape`

Synchronous. One request → one result.

### Tool: `fetch_page`
Grounded in `ScrapeConfig` (your `config.py`) + the TS SDK option list.

| Group | Options |
|---|---|
| Required | `url` |
| Common | `render_js`, `asp`, `country`, `cache`, `cache_ttl`, `auto_scroll`, `rendering_wait`, `wait_for_selector` |
| Advanced | `method`, `headers`, `body`, `js_scenario`, `geolocation`, `format` (`raw`/`text`/`markdown`/`clean_html`), `cost_budget` |

**Returns:** `{ url, content, status_code, from_cache, credits_used, log_url }` (same distillation as `ScrapeResult`).

### Tool: `account_info`
No parameters. Returns remaining credits / subscription usage. **Free** (no scrape credits). Intended as a pre-flight before a large crawl.

### Tool: `take_screenshot`
| Group | Options |
|---|---|
| Required | `url` |
| Common | `format` (`png`/`jpg`), `full_page`, `capture` (CSS selector for element), `resolution`, `country`, `render_js`, `rendering_wait` |

**Returns:** image reference/bytes + `credits_used`. Uses the SDK screenshot method if present, else REST `api.scrapfly.io/screenshot` (verify at build, §9).

## 6. Crawl server — `scrapfly-crawl`

Asynchronous job lifecycle, mirroring `crawler_client.py`.

| Tool | Purpose | Options |
|---|---|---|
| `start_crawl` | begin crawl, return `crawler_uuid` | `url`, `page_limit`, `max_depth`, `content_formats`, `include_only_paths`, `exclude_paths`, `asp`, `country`, `proxy_pool`, `respect_robots_txt`, `use_sitemaps`, `ignore_no_follow`, `ignore_base_path_restriction`, `max_duration`, `delay`, `rendering_delay`, `cache`, `cache_ttl`, `max_api_credit`, `max_concurrency` |
| `crawl_status` | progress for a uuid | `crawler_uuid` → `{ status, is_finished, is_success, urls_visited, urls_to_crawl, urls_failed, urls_extracted, urls_skipped, api_credit_used, duration, stop_reason }` |
| `crawl_contents` | fetch crawled content | `crawler_uuid`, `format` (default `markdown`), `url?` |
| `list_crawled_urls` | list visited/failed URLs | `crawler_uuid`, `status?`, `page?`, `per_page?` |
| `cancel_crawl` | stop a running crawl | `crawler_uuid` |

### Key design decision: no blocking poll
The Python `poll()` (a `while True: sleep(10)` loop) is **not** ported as a tool. An MCP tool that blocks for minutes holds the stdio connection open, risks client timeouts, and starves the agent of other actions. Instead:
- `start_crawl` returns a `crawler_uuid` immediately.
- The **agent** decides when to call `crawl_status` again (its own turn-taking is the polling loop).
- Transient 429 backoff still happens **inside** each tool call (via `core/retry.ts`); only the long-horizon waiting moves to the agent.

## 7. Cross-cutting concerns

### API key
- Read from `SCRAPFLY_API_KEY` in `core.createClient()`.
- Injected per-server via the `env` block in `.claude.json` at registration; recovered from the legacy `/home/kasey/.claude.json` entry.
- Never hardcoded; never committed (lives in Claude config, not in `infrastructure/`).

### Error handling
- `core/errors.ts` maps `ScrapflyError` / HTTP errors to a structured tool error carrying `code`, human message, `is_retryable`, and `credits_used` where available.
- 429 → bounded exponential backoff (max 5 retries) inside the call, honoring `Retry-After`.
- Upstream scrape errors raised (parity with `raise_on_upstream_error=True`).

### Registration (user scope)
```
claude mcp add --transport stdio --scope user scrapfly-scrape \
  --env SCRAPFLY_API_KEY=<recovered> -- node <abs>/packages/scrape-server/build/index.js
claude mcp add --transport stdio --scope user scrapfly-crawl \
  --env SCRAPFLY_API_KEY=<recovered> -- node <abs>/packages/crawl-server/build/index.js
```
Then update `~/.claude/settings.json` allow-list: replace `mcp__scrapfly-cloud-mcp__*` with `mcp__scrapfly-scrape__*` and `mcp__scrapfly-crawl__*`.

### Testing
- **Unit (no network):** args → Scrapfly config/body mapping; error mapping; 429 backoff timing.
- **Integration (credit-costing, env-flag gated):** one `fetch_page` against a trivial page; one tiny bounded crawl (`page_limit: 2`). Never run in CI by default.

## 8. Relationship to the "one repo" goal
The workspace root is `scrapfly-mcp/` (its own `package.json`/lockfile), so when `infrastructure/` is later `git init`'d as a single repo, this monorepo nests as a normal subtree without root-level workspace wiring. The repo-level `.gitignore` must exclude `node_modules/`, `build/`, `.env`, and any credential files.

## 9. Open risks / verify-at-build
1. **Does the TS `scrapfly-sdk` actually expose the crawler?** Docs say yes (`Crawl` helper: `start/status/urls/read/cancel`); GitHub excerpt was inconclusive. If not, `crawl-server` calls REST `api.scrapfly.io/crawl/...` directly (exactly like the Python client). Decided per evidence at build.
2. **Screenshot method name** in the TS SDK (`client.screenshot()` vs REST `/screenshot`). Verify; REST fallback otherwise.
3. **`@modelcontextprotocol/sdk` version** to pin — align with the newest used in `mcp-d2-diagrams` (`^1.11.4`) or later.

## 10. Out of scope (future)
- Extraction / AI parsing tools.
- WARC/HAR artifact download tools (`crawl.warc()`/`har()`).
- Publishing the servers as standalone npm packages.
