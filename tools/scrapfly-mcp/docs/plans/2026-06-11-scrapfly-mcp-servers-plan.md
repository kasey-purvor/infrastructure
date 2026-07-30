# Scrapfly MCP Servers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two local TypeScript MCP servers — `scrapfly-scrape` (synchronous single-page scrape + screenshot + account) and `scrapfly-crawl` (async crawl job lifecycle) — over the official `scrapfly-sdk`, sharing a `core` package, then register and live-test them.

**Architecture:** An npm-workspaces monorepo at `infrastructure/tools/scrapfly-mcp/` with three packages: `core` (client factory, env/key loading, error mapping, shared zod option fragments, MCP result helpers), `scrape-server`, and `crawl-server`. Each tool is split into a pure `build*Options(args)` mapper, a pure `distill*(result)` shaper, and an injectable `run*(client, args)` handler so logic is unit-testable without the network. Servers use `McpServer` + `registerTool`; the API key is read from `SCRAPFLY_API_KEY` and injected at registration.

**Tech Stack:** TypeScript (ES2022, NodeNext ESM), `@modelcontextprotocol/sdk@^1.11.4`, `scrapfly-sdk@^0.11.0`, `zod@^3.25.16`, `vitest` (tests), Node ≥ 20.

**Verified API facts (from installed `.d.ts`, scrapfly-sdk 0.11.0):**
- Import: `import { ScrapflyClient, ScrapeConfig, ScreenshotConfig, CrawlerConfig } from 'scrapfly-sdk'`.
- Client: `new ScrapflyClient({ key })`.
- Scrape: `await client.scrape(new ScrapeConfig(opts))` → `result.result.content` / `.result.status_code` / `.result.log_url` / `.result.url`; credits `result.context.cost.total`; cache `result.context.cache.state === 'HIT'`.
- Screenshot: `await client.screenshot(new ScreenshotConfig(opts))` → `.image` is an `ArrayBuffer`; `.metadata = { extension_name, upstream_status_code, upstream_url }`. `capture` is a string (`'fullpage'|'viewport'|`selector).
- Account: `await client.account()` → `acct.subscription.usage.scrape.{remaining,limit,current,extra,concurrent_remaining,concurrent_limit,concurrent_usage}`, `acct.subscription.plan_name`, `acct.subscription.period.{start,end}`, `acct.project.quota_reached`.
- Crawl (low-level, non-blocking, all on the client):
  - `await client.crawl(new CrawlerConfig(opts))` → `{ crawler_uuid: string; status: string }`.
  - `await client.crawlStatus(uuid)` → `CrawlerStatus { crawler_uuid, status: 'PENDING'|'RUNNING'|'DONE'|'CANCELLED', is_finished, is_success: boolean|null, state: { urls_visited, urls_extracted, urls_failed, urls_skipped, urls_to_crawl, api_credit_used, duration, stop_reason } }`.
  - `await client.crawlContents(uuid, { format, url?, plain?, limit?, offset? })` → `CrawlerContents { contents, links }` (JSON mode).
  - `await client.crawlUrls(uuid, { status?, page?, per_page? })` → `CrawlerUrls { urls: { url, status?, reason? }[], page, per_page }`.
  - `await client.crawlCancel(uuid)` → `boolean`.
  - `CrawlerContentFormat = 'html'|'clean_html'|'markdown'|'text'|'json'|'extracted_data'|'page_metadata'`.

**Git note:** `infrastructure/` is not yet a git repo. This plan initializes git **scoped to `scrapfly-mcp/`** for TDD commits. Task 19 (the final consolidation into one `infrastructure` GitHub repo) addresses flattening the inner `.git`. Per the user's standing instruction, **no commit or PR may include any Claude attribution / co-author trailer.**

---

## File Structure

```
infrastructure/tools/scrapfly-mcp/
  package.json                      # workspaces root
  tsconfig.base.json
  .gitignore
  README.md
  docs/specs/2026-06-11-scrapfly-mcp-servers-design.md   # (exists)
  docs/plans/2026-06-11-scrapfly-mcp-servers-plan.md      # (this file)
  packages/
    core/
      package.json
      tsconfig.json
      src/
        config.ts        # loadApiKey(env)
        client.ts        # createClient(apiKey?)
        errors.ts        # describeError(err)
        mcp.ts           # jsonResult / textResult / errorResult
        schemas.ts       # shared zod option fragments
        index.ts         # barrel
        config.test.ts
        errors.test.ts
    scrape-server/
      package.json
      tsconfig.json
      src/
        tools/
          fetch-page.ts        # schema + buildScrapeOptions + distillScrape + runFetchPage + registerFetchPage
          account-info.ts      # distillAccount + runAccountInfo + registerAccountInfo
          screenshot.ts        # schema + buildShotOptions + runScreenshot + registerScreenshot
          fetch-page.test.ts
          account-info.test.ts
          screenshot.test.ts
        server.ts              # createScrapeServer(client)
        index.ts               # shebang, stdio bootstrap
    crawl-server/
      package.json
      tsconfig.json
      src/
        tools/
          start-crawl.ts
          crawl-status.ts
          crawl-contents.ts
          list-crawled-urls.ts
          cancel-crawl.ts
          start-crawl.test.ts
          crawl-status.test.ts
        server.ts
        index.ts
```

---

## Task 1: Scaffold monorepo + git init

**Files:**
- Create: `infrastructure/tools/scrapfly-mcp/package.json`
- Create: `infrastructure/tools/scrapfly-mcp/tsconfig.base.json`
- Create: `infrastructure/tools/scrapfly-mcp/.gitignore`
- Create: `infrastructure/tools/scrapfly-mcp/README.md`

- [ ] **Step 1: Create the directory tree**

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp
mkdir -p packages/core/src packages/scrape-server/src/tools packages/crawl-server/src/tools
```

- [ ] **Step 2: Write root `package.json`**

```json
{
  "name": "scrapfly-mcp",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=20" },
  "workspaces": ["packages/*"],
  "scripts": {
    "build": "tsc --build",
    "typecheck": "tsc --build --dry || tsc -b",
    "test": "npm run test --workspaces --if-present",
    "clean": "rm -rf packages/*/build packages/*/*.tsbuildinfo"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "typescript": "^5.8.3"
  }
}
```

- [ ] **Step 3: Write `tsconfig.base.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022"],
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "composite": true
  }
}
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
node_modules/
build/
dist/
*.tsbuildinfo
.env
.env.*
*.key
*.pem
.DS_Store
coverage/
```

- [ ] **Step 5: Write `README.md`**

```markdown
# scrapfly-mcp

Two local MCP servers over the official `scrapfly-sdk`:

- **scrapfly-scrape** — `fetch_page`, `account_info`, `take_screenshot` (synchronous).
- **scrapfly-crawl** — `start_crawl`, `crawl_status`, `crawl_contents`, `list_crawled_urls`, `cancel_crawl` (async job lifecycle; the agent polls `crawl_status`, the servers never block).

## Setup
```bash
npm install
npm run build
```
Set `SCRAPFLY_API_KEY` in the environment that launches each server (injected via the MCP client config).

See `docs/specs/` and `docs/plans/` for design and implementation detail.
```

- [ ] **Step 6: Initialize git and make the first commit**

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp
git init
git add -A
git -c user.name="$(git config --global user.name)" -c user.email="$(git config --global user.email)" commit -m "chore: scaffold scrapfly-mcp monorepo"
```
Expected: a commit is created; `git status` is clean. (Do **not** add any Claude co-author trailer.)

---

## Task 2: core — API key loader

**Files:**
- Create: `packages/core/src/config.ts`
- Test: `packages/core/src/config.test.ts`
- Create: `packages/core/package.json`, `packages/core/tsconfig.json`

- [ ] **Step 1: Write `packages/core/package.json`**

```json
{
  "name": "@scrapfly-mcp/core",
  "version": "0.1.0",
  "description": "Shared Scrapfly client, key loading, error mapping, and MCP helpers",
  "type": "module",
  "main": "build/index.js",
  "types": "build/index.d.ts",
  "exports": { ".": { "types": "./build/index.d.ts", "import": "./build/index.js" } },
  "files": ["build"],
  "scripts": {
    "build": "tsc -b",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.11.4",
    "scrapfly-sdk": "^0.11.0",
    "zod": "^3.25.16"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "typescript": "^5.8.3",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Write `packages/core/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": { "outDir": "./build", "rootDir": "./src" },
  "include": ["src/**/*"],
  "exclude": ["src/**/*.test.ts"]
}
```

- [ ] **Step 3: Install workspace deps from the repo root**

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm install
```
Expected: installs without error; `node_modules/scrapfly-sdk/package.json` shows `"version": "0.11.0"` (or newer 0.11.x).

- [ ] **Step 4: Write the failing test `packages/core/src/config.test.ts`**

```ts
import { describe, it, expect } from "vitest";
import { loadApiKey } from "./config.js";

describe("loadApiKey", () => {
  it("returns the key when SCRAPFLY_API_KEY is set", () => {
    expect(loadApiKey({ SCRAPFLY_API_KEY: "scp-live-abc" })).toBe("scp-live-abc");
  });

  it("throws a clear error when the key is missing", () => {
    expect(() => loadApiKey({})).toThrow(/SCRAPFLY_API_KEY/);
  });

  it("throws when the key is empty or whitespace", () => {
    expect(() => loadApiKey({ SCRAPFLY_API_KEY: "   " })).toThrow(/SCRAPFLY_API_KEY/);
  });
});
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd packages/core && npx vitest run src/config.test.ts`
Expected: FAIL — cannot find module `./config.js` / `loadApiKey` is not defined.

- [ ] **Step 6: Write `packages/core/src/config.ts`**

```ts
/** Reads the Scrapfly API key from an environment map. Defaults to process.env. */
export function loadApiKey(env: Record<string, string | undefined> = process.env): string {
  const key = env.SCRAPFLY_API_KEY;
  if (typeof key !== "string" || key.trim() === "") {
    throw new Error(
      "SCRAPFLY_API_KEY environment variable is not set. " +
        "Provide it via the MCP server's env block in your Claude config.",
    );
  }
  return key;
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd packages/core && npx vitest run src/config.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add packages/core
git commit -m "feat(core): add SCRAPFLY_API_KEY loader with validation"
```

---

## Task 3: core — Scrapfly client factory

**Files:**
- Create: `packages/core/src/client.ts`

- [ ] **Step 1: Write `packages/core/src/client.ts`**

```ts
import { ScrapflyClient } from "scrapfly-sdk";
import { loadApiKey } from "./config.js";

/**
 * Create a shared ScrapflyClient. One instance is safe across concurrent calls.
 * Pass an explicit key for tests; otherwise it is read from SCRAPFLY_API_KEY.
 */
export function createClient(apiKey: string = loadApiKey()): ScrapflyClient {
  return new ScrapflyClient({ key: apiKey });
}
```

- [ ] **Step 2: Typecheck (no test — thin wrapper over the SDK)**

Run: `cd packages/core && npx tsc --noEmit`
Expected: no type errors. (A real network test would cost credits; the factory is exercised by the gated integration test in Task 16.)

- [ ] **Step 3: Commit**

```bash
git add packages/core/src/client.ts
git commit -m "feat(core): add ScrapflyClient factory"
```

---

## Task 4: core — error description

**Files:**
- Create: `packages/core/src/errors.ts`
- Test: `packages/core/src/errors.test.ts`

- [ ] **Step 1: Write the failing test `packages/core/src/errors.test.ts`**

```ts
import { describe, it, expect } from "vitest";
import { describeError } from "./errors.js";

describe("describeError", () => {
  it("extracts message and code from an Error with scrapfly fields", () => {
    const err = Object.assign(new Error("upstream blocked"), {
      code: "ERR::ASP::SHIELD_PROTECTION_FAILED",
      retryable: true,
    });
    expect(describeError(err)).toEqual({
      message: "upstream blocked",
      retryable: true,
      code: "ERR::ASP::SHIELD_PROTECTION_FAILED",
    });
  });

  it("defaults retryable to false for a plain Error", () => {
    expect(describeError(new Error("boom"))).toEqual({ message: "boom", retryable: false });
  });

  it("stringifies non-Error throwables", () => {
    expect(describeError("nope")).toEqual({ message: "nope", retryable: false });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd packages/core && npx vitest run src/errors.test.ts`
Expected: FAIL — `describeError` is not defined.

- [ ] **Step 3: Write `packages/core/src/errors.ts`**

```ts
export interface ErrorDescription {
  message: string;
  retryable: boolean;
  code?: string;
}

/** Normalise an unknown thrown value into a structured, model-friendly description. */
export function describeError(err: unknown): ErrorDescription {
  if (err instanceof Error) {
    const e = err as Error & { code?: string; retryable?: boolean; is_retryable?: boolean };
    const out: ErrorDescription = {
      message: e.message,
      retryable: e.retryable ?? e.is_retryable ?? false,
    };
    if (typeof e.code === "string") out.code = e.code;
    return out;
  }
  return { message: String(err), retryable: false };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd packages/core && npx vitest run src/errors.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/src/errors.ts packages/core/src/errors.test.ts
git commit -m "feat(core): add describeError normaliser"
```

---

## Task 5: core — MCP result helpers, shared schemas, barrel

**Files:**
- Create: `packages/core/src/mcp.ts`
- Create: `packages/core/src/schemas.ts`
- Create: `packages/core/src/index.ts`

- [ ] **Step 1: Write `packages/core/src/mcp.ts`**

```ts
import { describeError } from "./errors.js";

/** Minimal shape of an MCP tool result (subset of CallToolResult we produce). */
export interface ToolResult {
  content: Array<{ type: "text"; text: string } | { type: "image"; data: string; mimeType: string }>;
  isError?: boolean;
}

/** Pretty-printed JSON as a text result. */
export function jsonResult(value: unknown): ToolResult {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

/** Plain text result. */
export function textResult(text: string): ToolResult {
  return { content: [{ type: "text", text }] };
}

/** Error result: returned (not thrown) so the model sees the failure as tool output. */
export function errorResult(err: unknown): ToolResult {
  const { message, retryable, code } = describeError(err);
  const prefix = code ? `[${code}] ` : "";
  const suffix = retryable ? " (retryable: you may try again)" : "";
  return { content: [{ type: "text", text: `${prefix}${message}${suffix}` }], isError: true };
}
```

- [ ] **Step 2: Write `packages/core/src/schemas.ts`** (shared zod option fragments — spread into tool input schemas)

```ts
import { z } from "zod";

/** Proxy + cache options shared by scrape, screenshot, and crawl tools. */
export const proxyCacheShape = {
  asp: z.boolean().optional().describe("Enable Scrapfly Anti-Scraping Protection (anti-bot bypass)."),
  country: z.string().length(2).optional().describe("ISO 3166 country code for the proxy, e.g. 'us', 'gb'."),
  cache: z.boolean().optional().describe("Serve from Scrapfly cache when a fresh entry exists."),
  cache_ttl: z.number().int().positive().optional().describe("Cache time-to-live in seconds."),
};
```

- [ ] **Step 3: Write `packages/core/src/index.ts`** (barrel)

```ts
export { loadApiKey } from "./config.js";
export { createClient } from "./client.js";
export { describeError, type ErrorDescription } from "./errors.js";
export { jsonResult, textResult, errorResult, type ToolResult } from "./mcp.js";
export { proxyCacheShape } from "./schemas.js";
```

- [ ] **Step 4: Build core and verify output**

Run: `cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm run build -w @scrapfly-mcp/core`
Expected: `packages/core/build/index.js` and `index.d.ts` exist; no type errors.

- [ ] **Step 5: Commit**

```bash
git add packages/core
git commit -m "feat(core): add MCP result helpers, shared schemas, and barrel"
```

---

## Task 6: scrape-server — `fetch_page` tool

**Files:**
- Create: `packages/scrape-server/package.json`, `packages/scrape-server/tsconfig.json`
- Create: `packages/scrape-server/src/tools/fetch-page.ts`
- Test: `packages/scrape-server/src/tools/fetch-page.test.ts`

- [ ] **Step 1: Write `packages/scrape-server/package.json`**

```json
{
  "name": "@scrapfly-mcp/scrape-server",
  "version": "0.1.0",
  "description": "MCP server exposing Scrapfly single-page scrape, screenshot, and account tools",
  "type": "module",
  "main": "build/index.js",
  "bin": { "scrapfly-scrape-server": "./build/index.js" },
  "files": ["build"],
  "scripts": {
    "build": "tsc -b",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.11.4",
    "@scrapfly-mcp/core": "*",
    "scrapfly-sdk": "^0.11.0",
    "zod": "^3.25.16"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "typescript": "^5.8.3",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Write `packages/scrape-server/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": { "outDir": "./build", "rootDir": "./src" },
  "include": ["src/**/*"],
  "exclude": ["src/**/*.test.ts"],
  "references": [{ "path": "../core" }]
}
```

- [ ] **Step 3: Re-install so the workspace link + new deps resolve**

Run: `cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm install`
Expected: `@scrapfly-mcp/core` is symlinked into `packages/scrape-server/node_modules`.

- [ ] **Step 4: Write the failing test `packages/scrape-server/src/tools/fetch-page.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { buildScrapeOptions, distillScrape, runFetchPage } from "./fetch-page.js";

describe("buildScrapeOptions", () => {
  it("passes the url through and always sets raise_on_upstream_error", () => {
    const opts = buildScrapeOptions({ url: "https://example.com" });
    expect(opts.url).toBe("https://example.com");
    expect(opts.raise_on_upstream_error).toBe(true);
  });

  it("forwards provided options verbatim and omits undefined ones", () => {
    const opts = buildScrapeOptions({ url: "https://x.com", render_js: true, country: "us" });
    expect(opts.render_js).toBe(true);
    expect(opts.country).toBe("us");
    expect("asp" in opts).toBe(false);
  });
});

describe("distillScrape", () => {
  it("extracts the compact result shape from a ScrapeResult-like object", () => {
    const fake = {
      result: { content: "<html>", status_code: 200, log_url: "https://log", url: "https://final" },
      context: { cost: { total: 5 }, cache: { state: "HIT" } },
    };
    expect(distillScrape(fake as never)).toEqual({
      url: "https://final",
      content: "<html>",
      status_code: 200,
      from_cache: true,
      credits_used: 5,
      log_url: "https://log",
    });
  });
});

describe("runFetchPage", () => {
  it("calls client.scrape and returns a JSON text result", async () => {
    const client = {
      scrape: vi.fn().mockResolvedValue({
        result: { content: "ok", status_code: 200, log_url: "l", url: "u" },
        context: { cost: { total: 1 }, cache: { state: "MISS" } },
      }),
    };
    const res = await runFetchPage(client as never, { url: "https://example.com" });
    expect(client.scrape).toHaveBeenCalledOnce();
    expect(res.isError).toBeUndefined();
    expect(res.content[0]).toMatchObject({ type: "text" });
    expect(res.content[0].type === "text" && res.content[0].text).toContain('"from_cache": false');
  });

  it("returns an error result (not a throw) when the client throws", async () => {
    const client = { scrape: vi.fn().mockRejectedValue(new Error("blocked")) };
    const res = await runFetchPage(client as never, { url: "https://example.com" });
    expect(res.isError).toBe(true);
    expect(res.content[0].type === "text" && res.content[0].text).toContain("blocked");
  });
});
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd packages/scrape-server && npx vitest run`
Expected: FAIL — module `./fetch-page.js` not found.

- [ ] **Step 6: Write `packages/scrape-server/src/tools/fetch-page.ts`**

```ts
import { z } from "zod";
import { ScrapeConfig, type ScrapflyClient, type ScrapeResult } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, proxyCacheShape, type ToolResult } from "@scrapfly-mcp/core";

export const fetchPageInputSchema = {
  url: z.string().url().describe("Absolute URL of the page to scrape."),
  render_js: z.boolean().optional().describe("Render in a real headless browser (enables JS, scrolling, waits)."),
  ...proxyCacheShape,
  auto_scroll: z.boolean().optional().describe("Scroll to page bottom before capture (requires render_js)."),
  rendering_wait: z.number().int().nonnegative().optional().describe("Extra ms to wait after load (requires render_js)."),
  wait_for_selector: z.string().optional().describe("CSS selector to wait for before reading (requires render_js)."),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "HEAD"]).optional().describe("Upstream HTTP method."),
  headers: z.record(z.string()).optional().describe("Custom request headers."),
  body: z.string().optional().describe("Raw request body for POST/PUT."),
  js_scenario: z.record(z.any()).optional().describe("Declarative browser automation steps (requires render_js)."),
  geolocation: z.string().optional().describe("Spoof geolocation as 'lat,lng'."),
  format: z.enum(["json", "text", "markdown", "clean_html", "raw"]).optional().describe("Output content format."),
  cost_budget: z.number().int().positive().optional().describe("Max API credits allowed for this scrape."),
};

const inputObject = z.object(fetchPageInputSchema);
export type FetchPageArgs = z.infer<typeof inputObject>;

/** Pure: map validated args to ScrapeConfig constructor options. */
export function buildScrapeOptions(args: FetchPageArgs): ConstructorParameters<typeof ScrapeConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url, raise_on_upstream_error: true };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  return opts as ConstructorParameters<typeof ScrapeConfig>[0];
}

/** Pure: distil a ScrapeResult into the compact response. */
export function distillScrape(result: ScrapeResult) {
  return {
    url: result.result.url,
    content: result.result.content,
    status_code: result.result.status_code,
    from_cache: result.context.cache?.state === "HIT",
    credits_used: result.context.cost?.total,
    log_url: result.result.log_url,
  };
}

/** Injectable handler: testable with a fake client. */
export async function runFetchPage(
  client: Pick<ScrapflyClient, "scrape">,
  args: FetchPageArgs,
): Promise<ToolResult> {
  try {
    const result = (await client.scrape(new ScrapeConfig(buildScrapeOptions(args)))) as ScrapeResult;
    return jsonResult(distillScrape(result));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerFetchPage(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "fetch_page",
    {
      title: "Fetch a web page (Scrapfly scrape)",
      description:
        "Scrape ONE page and return its content. Use render_js for JS-heavy sites, asp to bypass anti-bot, " +
        "format='markdown' for clean text. Synchronous — returns the page in one call.",
      inputSchema: fetchPageInputSchema,
    },
    async (args) => runFetchPage(client, args as FetchPageArgs),
  );
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd packages/scrape-server && npx vitest run`
Expected: PASS (all `fetch-page` tests).

- [ ] **Step 8: Commit**

```bash
git add packages/scrape-server
git commit -m "feat(scrape): add fetch_page tool with full option surface"
```

---

## Task 7: scrape-server — `account_info` tool

**Files:**
- Create: `packages/scrape-server/src/tools/account-info.ts`
- Test: `packages/scrape-server/src/tools/account-info.test.ts`

- [ ] **Step 1: Write the failing test `account-info.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { distillAccount, runAccountInfo } from "./account-info.js";

const fakeAccount = {
  subscription: {
    plan_name: "Pro",
    period: { start: "2026-06-01", end: "2026-07-01" },
    usage: {
      scrape: {
        current: 100, limit: 1000, remaining: 900, extra: 0,
        concurrent_limit: 20, concurrent_remaining: 20, concurrent_usage: 0,
      },
    },
  },
  project: { quota_reached: false },
};

describe("distillAccount", () => {
  it("pulls plan, period, scrape credits, and concurrency", () => {
    expect(distillAccount(fakeAccount as never)).toEqual({
      plan: "Pro",
      period: { start: "2026-06-01", end: "2026-07-01" },
      scrape_credits: { remaining: 900, limit: 1000, current: 100, extra: 0 },
      concurrency: { remaining: 20, limit: 20, in_use: 0 },
      quota_reached: false,
    });
  });
});

describe("runAccountInfo", () => {
  it("calls client.account and returns a JSON result", async () => {
    const client = { account: vi.fn().mockResolvedValue(fakeAccount) };
    const res = await runAccountInfo(client as never);
    expect(client.account).toHaveBeenCalledOnce();
    expect(res.content[0].type === "text" && res.content[0].text).toContain('"remaining": 900');
  });
});
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `cd packages/scrape-server && npx vitest run src/tools/account-info.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `account-info.ts`**

```ts
import type { ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

type AccountData = Awaited<ReturnType<ScrapflyClient["account"]>>;

export function distillAccount(acct: AccountData) {
  const s = acct.subscription;
  const u = s.usage.scrape;
  return {
    plan: s.plan_name,
    period: { start: s.period.start, end: s.period.end },
    scrape_credits: { remaining: u.remaining, limit: u.limit, current: u.current, extra: u.extra },
    concurrency: { remaining: u.concurrent_remaining, limit: u.concurrent_limit, in_use: u.concurrent_usage },
    quota_reached: acct.project.quota_reached,
  };
}

export async function runAccountInfo(client: Pick<ScrapflyClient, "account">): Promise<ToolResult> {
  try {
    return jsonResult(distillAccount(await client.account()));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerAccountInfo(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "account_info",
    {
      title: "Scrapfly account / credit status",
      description: "Return remaining scrape credits, concurrency, plan, and billing period. Free — costs no credits.",
      inputSchema: {},
    },
    async () => runAccountInfo(client),
  );
}
```

- [ ] **Step 4: Run test, verify PASS**

Run: `cd packages/scrape-server && npx vitest run src/tools/account-info.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/scrape-server/src/tools/account-info.ts packages/scrape-server/src/tools/account-info.test.ts
git commit -m "feat(scrape): add account_info tool"
```

---

## Task 8: scrape-server — `take_screenshot` tool

**Files:**
- Create: `packages/scrape-server/src/tools/screenshot.ts`
- Test: `packages/scrape-server/src/tools/screenshot.test.ts`

- [ ] **Step 1: Write the failing test `screenshot.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { buildShotOptions, mimeForFormat, runScreenshot } from "./screenshot.js";

describe("buildShotOptions", () => {
  it("passes url + capture through, omits undefined", () => {
    const o = buildShotOptions({ url: "https://x.com", capture: "fullpage" });
    expect(o).toEqual({ url: "https://x.com", capture: "fullpage" });
  });
});

describe("mimeForFormat", () => {
  it("maps formats to mime types, defaulting to jpeg", () => {
    expect(mimeForFormat("png")).toBe("image/png");
    expect(mimeForFormat(undefined)).toBe("image/jpeg");
  });
});

describe("runScreenshot", () => {
  it("returns an image content block with base64 data", async () => {
    const bytes = new Uint8Array([1, 2, 3]).buffer;
    const client = { screenshot: vi.fn().mockResolvedValue({ image: bytes, metadata: { extension_name: "png" } }) };
    const res = await runScreenshot(client as never, { url: "https://x.com", format: "png" });
    expect(client.screenshot).toHaveBeenCalledOnce();
    expect(res.content[0]).toMatchObject({ type: "image", mimeType: "image/png" });
    expect(res.content[0].type === "image" && res.content[0].data).toBe(Buffer.from(bytes).toString("base64"));
  });

  it("returns an error result when the client throws", async () => {
    const client = { screenshot: vi.fn().mockRejectedValue(new Error("nope")) };
    const res = await runScreenshot(client as never, { url: "https://x.com" });
    expect(res.isError).toBe(true);
  });
});
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `cd packages/scrape-server && npx vitest run src/tools/screenshot.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `screenshot.ts`**

```ts
import { z } from "zod";
import { ScreenshotConfig, type ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const screenshotInputSchema = {
  url: z.string().url().describe("Absolute URL of the page to screenshot."),
  format: z.enum(["jpg", "png", "webp", "gif"]).optional().describe("Image format (default jpg)."),
  capture: z.string().optional().describe("Capture area: 'fullpage', 'viewport', or a CSS selector."),
  resolution: z.string().optional().describe("Viewport resolution as 'WIDTHxHEIGHT', e.g. '1920x1080'."),
  country: z.string().length(2).optional().describe("ISO country code for the rendering proxy."),
  rendering_wait: z.number().int().nonnegative().optional().describe("Extra ms to wait after load before capture."),
  wait_for_selector: z.string().optional().describe("CSS selector to wait for before capture."),
  auto_scroll: z.boolean().optional().describe("Scroll to the bottom before capturing."),
};

const shotObject = z.object(screenshotInputSchema);
export type ScreenshotArgs = z.infer<typeof shotObject>;

export function buildShotOptions(args: ScreenshotArgs): ConstructorParameters<typeof ScreenshotConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  return opts as ConstructorParameters<typeof ScreenshotConfig>[0];
}

export function mimeForFormat(format: ScreenshotArgs["format"]): string {
  switch (format) {
    case "png": return "image/png";
    case "webp": return "image/webp";
    case "gif": return "image/gif";
    default: return "image/jpeg";
  }
}

export async function runScreenshot(
  client: Pick<ScrapflyClient, "screenshot">,
  args: ScreenshotArgs,
): Promise<ToolResult> {
  try {
    const shot = await client.screenshot(new ScreenshotConfig(buildShotOptions(args)));
    const data = Buffer.from(shot.image).toString("base64");
    return { content: [{ type: "image", data, mimeType: mimeForFormat(args.format) }] };
  } catch (err) {
    return errorResult(err);
  }
}

export function registerScreenshot(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "take_screenshot",
    {
      title: "Screenshot a web page (Scrapfly)",
      description: "Capture a PNG/JPG screenshot of a page. Use capture='fullpage' for the whole page or a CSS selector for one element.",
      inputSchema: screenshotInputSchema,
    },
    async (args) => runScreenshot(client, args as ScreenshotArgs),
  );
}
```

- [ ] **Step 4: Run test, verify PASS**

Run: `cd packages/scrape-server && npx vitest run src/tools/screenshot.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/scrape-server/src/tools/screenshot.ts packages/scrape-server/src/tools/screenshot.test.ts
git commit -m "feat(scrape): add take_screenshot tool returning an image block"
```

---

## Task 9: scrape-server — server assembly + entry + build

**Files:**
- Create: `packages/scrape-server/src/server.ts`
- Create: `packages/scrape-server/src/index.ts`

- [ ] **Step 1: Write `packages/scrape-server/src/server.ts`**

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@scrapfly-mcp/core";
import type { ScrapflyClient } from "scrapfly-sdk";
import { registerFetchPage } from "./tools/fetch-page.js";
import { registerAccountInfo } from "./tools/account-info.js";
import { registerScreenshot } from "./tools/screenshot.js";

/** Build the scrape MCP server. Inject a client for tests; defaults to env-configured. */
export function createScrapeServer(client: ScrapflyClient = createClient()): McpServer {
  const server = new McpServer({ name: "scrapfly-scrape", version: "0.1.0" });
  registerFetchPage(server, client);
  registerAccountInfo(server, client);
  registerScreenshot(server, client);
  return server;
}
```

- [ ] **Step 2: Write `packages/scrape-server/src/index.ts`**

```ts
#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createScrapeServer } from "./server.js";

async function main(): Promise<void> {
  const server = createScrapeServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stdout is the JSON-RPC channel — log only to stderr.
  console.error("[scrapfly-scrape] running on stdio");
}

main().catch((error) => {
  console.error("[scrapfly-scrape] fatal:", error);
  process.exit(1);
});
```

- [ ] **Step 3: Build the scrape server**

Run: `cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm run build -w @scrapfly-mcp/scrape-server`
Expected: `packages/scrape-server/build/index.js` exists with a `#!/usr/bin/env node` first line.

- [ ] **Step 4: Smoke-start the server (no key needed to boot; it lazily creates the client)**

> Note: `createClient()` calls `loadApiKey()` at server construction, so a boot smoke test needs a dummy key. Verify it starts then exits cleanly on stdin EOF:

Run:
```bash
SCRAPFLY_API_KEY=scp-live-dummy node packages/scrape-server/build/index.js <<< "" 2>&1 | head -2
```
Expected: prints `[scrapfly-scrape] running on stdio` to stderr, then exits when stdin closes. (No crash, no stdout noise.)

- [ ] **Step 5: Commit**

```bash
git add packages/scrape-server/src/server.ts packages/scrape-server/src/index.ts
git commit -m "feat(scrape): assemble McpServer and stdio entrypoint"
```

---

## Task 10: crawl-server — `start_crawl` tool

**Files:**
- Create: `packages/crawl-server/package.json`, `packages/crawl-server/tsconfig.json`
- Create: `packages/crawl-server/src/tools/start-crawl.ts`
- Test: `packages/crawl-server/src/tools/start-crawl.test.ts`

- [ ] **Step 1: Write `packages/crawl-server/package.json`** (clone of scrape-server with crawl names)

```json
{
  "name": "@scrapfly-mcp/crawl-server",
  "version": "0.1.0",
  "description": "MCP server exposing the Scrapfly crawler job lifecycle as tools",
  "type": "module",
  "main": "build/index.js",
  "bin": { "scrapfly-crawl-server": "./build/index.js" },
  "files": ["build"],
  "scripts": { "build": "tsc -b", "typecheck": "tsc --noEmit", "test": "vitest run" },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.11.4",
    "@scrapfly-mcp/core": "*",
    "scrapfly-sdk": "^0.11.0",
    "zod": "^3.25.16"
  },
  "devDependencies": {
    "@types/node": "^22.15.21",
    "typescript": "^5.8.3",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Write `packages/crawl-server/tsconfig.json`** (identical to scrape-server's)

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": { "outDir": "./build", "rootDir": "./src" },
  "include": ["src/**/*"],
  "exclude": ["src/**/*.test.ts"],
  "references": [{ "path": "../core" }]
}
```

- [ ] **Step 3: Re-install for the new workspace package**

Run: `cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm install`

- [ ] **Step 4: Write the failing test `start-crawl.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { buildCrawlOptions, runStartCrawl } from "./start-crawl.js";

describe("buildCrawlOptions", () => {
  it("requires url and forwards crawl options, omitting undefined", () => {
    const o = buildCrawlOptions({ url: "https://x.com", page_limit: 10, asp: true });
    expect(o).toMatchObject({ url: "https://x.com", page_limit: 10, asp: true });
    expect("country" in o).toBe(false);
  });
});

describe("runStartCrawl", () => {
  it("calls client.crawl and returns the uuid + status", async () => {
    const client = { crawl: vi.fn().mockResolvedValue({ crawler_uuid: "abc", status: "PENDING" }) };
    const res = await runStartCrawl(client as never, { url: "https://x.com" });
    expect(client.crawl).toHaveBeenCalledOnce();
    expect(res.content[0].type === "text" && res.content[0].text).toContain('"crawler_uuid": "abc"');
  });

  it("returns an error result when the client throws", async () => {
    const client = { crawl: vi.fn().mockRejectedValue(new Error("bad config")) };
    const res = await runStartCrawl(client as never, { url: "https://x.com" });
    expect(res.isError).toBe(true);
  });
});
```

- [ ] **Step 5: Run test, verify FAIL**

Run: `cd packages/crawl-server && npx vitest run src/tools/start-crawl.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 6: Write `start-crawl.ts`**

```ts
import { z } from "zod";
import { CrawlerConfig, type ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, proxyCacheShape, type ToolResult } from "@scrapfly-mcp/core";

const CONTENT_FORMATS = ["html", "clean_html", "markdown", "text", "json", "extracted_data", "page_metadata"] as const;

export const startCrawlInputSchema = {
  url: z.string().url().describe("Seed URL to start crawling from."),
  page_limit: z.number().int().positive().optional().describe("Max number of pages to crawl."),
  max_depth: z.number().int().nonnegative().optional().describe("Max link depth from the seed."),
  max_duration: z.number().int().positive().optional().describe("Max crawl wall-clock duration in seconds."),
  max_api_credit: z.number().int().positive().optional().describe("Max API credits the crawl may consume."),
  max_concurrency: z.number().int().positive().optional().describe("Max concurrent fetches."),
  content_formats: z.array(z.enum(CONTENT_FORMATS)).optional().describe("Content representations to store per page."),
  include_only_paths: z.array(z.string()).optional().describe("Restrict crawl to these URL path patterns."),
  exclude_paths: z.array(z.string()).optional().describe("URL path patterns to exclude."),
  ignore_base_path_restriction: z.boolean().optional().describe("Allow crawling outside the seed's base path."),
  follow_internal_subdomains: z.boolean().optional().describe("Follow links into subdomains of the seed domain."),
  respect_robots_txt: z.boolean().optional().describe("Honor robots.txt (server default true)."),
  use_sitemaps: z.boolean().optional().describe("Seed the crawl from the site's sitemaps."),
  ignore_no_follow: z.boolean().optional().describe("Follow rel=nofollow links anyway."),
  delay: z.number().int().nonnegative().optional().describe("Delay between requests."),
  rendering_delay: z.number().int().nonnegative().optional().describe("Delay after render before reading."),
  proxy_pool: z.string().optional().describe("Proxy pool name for the crawl."),
  ...proxyCacheShape,
};

const crawlObject = z.object(startCrawlInputSchema);
export type StartCrawlArgs = z.infer<typeof crawlObject>;

export function buildCrawlOptions(args: StartCrawlArgs): ConstructorParameters<typeof CrawlerConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  return opts as ConstructorParameters<typeof CrawlerConfig>[0];
}

export async function runStartCrawl(
  client: Pick<ScrapflyClient, "crawl">,
  args: StartCrawlArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, status } = await client.crawl(new CrawlerConfig(buildCrawlOptions(args)));
    return jsonResult({ crawler_uuid, status });
  } catch (err) {
    return errorResult(err);
  }
}

export function registerStartCrawl(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "start_crawl",
    {
      title: "Start a Scrapfly crawl",
      description:
        "Begin an ASYNC crawl from a seed URL and return a crawler_uuid immediately. " +
        "Then poll crawl_status with that uuid until is_finished is true; fetch pages with crawl_contents.",
      inputSchema: startCrawlInputSchema,
    },
    async (args) => runStartCrawl(client, args as StartCrawlArgs),
  );
}
```

- [ ] **Step 7: Run test, verify PASS**

Run: `cd packages/crawl-server && npx vitest run src/tools/start-crawl.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add packages/crawl-server
git commit -m "feat(crawl): add start_crawl tool"
```

---

## Task 11: crawl-server — `crawl_status` tool

**Files:**
- Create: `packages/crawl-server/src/tools/crawl-status.ts`
- Test: `packages/crawl-server/src/tools/crawl-status.test.ts`

- [ ] **Step 1: Write the failing test `crawl-status.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { distillStatus, runCrawlStatus } from "./crawl-status.js";

const fakeStatus = {
  crawler_uuid: "abc",
  status: "RUNNING",
  is_finished: false,
  is_success: null,
  state: {
    urls_visited: 5, urls_extracted: 4, urls_failed: 1, urls_skipped: 0,
    urls_to_crawl: 12, api_credit_used: 30, duration: 9, stop_reason: null,
  },
};

describe("distillStatus", () => {
  it("flattens status + state metrics", () => {
    expect(distillStatus(fakeStatus as never)).toEqual({
      crawler_uuid: "abc",
      status: "RUNNING",
      is_finished: false,
      is_success: null,
      urls_visited: 5, urls_extracted: 4, urls_failed: 1, urls_skipped: 0,
      urls_to_crawl: 12, api_credit_used: 30, duration: 9, stop_reason: null,
    });
  });
});

describe("runCrawlStatus", () => {
  it("calls client.crawlStatus with the uuid", async () => {
    const client = { crawlStatus: vi.fn().mockResolvedValue(fakeStatus) };
    const res = await runCrawlStatus(client as never, { crawler_uuid: "abc" });
    expect(client.crawlStatus).toHaveBeenCalledWith("abc");
    expect(res.content[0].type === "text" && res.content[0].text).toContain('"urls_visited": 5');
  });
});
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `cd packages/crawl-server && npx vitest run src/tools/crawl-status.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write `crawl-status.ts`**

```ts
import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const crawlStatusInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
};
const obj = z.object(crawlStatusInputSchema);
export type CrawlStatusArgs = z.infer<typeof obj>;

type CrawlerStatus = Awaited<ReturnType<ScrapflyClient["crawlStatus"]>>;

export function distillStatus(s: CrawlerStatus) {
  return {
    crawler_uuid: s.crawler_uuid,
    status: s.status,
    is_finished: s.is_finished,
    is_success: s.is_success,
    urls_visited: s.state.urls_visited,
    urls_extracted: s.state.urls_extracted,
    urls_failed: s.state.urls_failed,
    urls_skipped: s.state.urls_skipped,
    urls_to_crawl: s.state.urls_to_crawl,
    api_credit_used: s.state.api_credit_used,
    duration: s.state.duration,
    stop_reason: s.state.stop_reason,
  };
}

export async function runCrawlStatus(
  client: Pick<ScrapflyClient, "crawlStatus">,
  args: CrawlStatusArgs,
): Promise<ToolResult> {
  try {
    return jsonResult(distillStatus(await client.crawlStatus(args.crawler_uuid)));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCrawlStatus(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "crawl_status",
    {
      title: "Check Scrapfly crawl status",
      description: "Return progress for a crawler_uuid. Poll this until is_finished is true (status 'DONE'); is_success tells you if it succeeded.",
      inputSchema: crawlStatusInputSchema,
    },
    async (args) => runCrawlStatus(client, args as CrawlStatusArgs),
  );
}
```

- [ ] **Step 4: Run test, verify PASS**

Run: `cd packages/crawl-server && npx vitest run src/tools/crawl-status.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/crawl-server/src/tools/crawl-status.ts packages/crawl-server/src/tools/crawl-status.test.ts
git commit -m "feat(crawl): add crawl_status tool"
```

---

## Task 12: crawl-server — `crawl_contents` tool

**Files:**
- Create: `packages/crawl-server/src/tools/crawl-contents.ts`

- [ ] **Step 1: Write `crawl-contents.ts`** (thin pass-through; distil is trivial so no separate unit test beyond typecheck — the JSON envelope is returned as-is)

```ts
import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

const CONTENT_FORMATS = ["html", "clean_html", "markdown", "text", "json", "extracted_data", "page_metadata"] as const;

export const crawlContentsInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
  format: z.enum(CONTENT_FORMATS).default("markdown").describe("Content representation to return (default markdown)."),
  url: z.string().url().optional().describe("If given, return only this crawled URL's content."),
  limit: z.number().int().positive().optional().describe("Max number of pages to return."),
  offset: z.number().int().nonnegative().optional().describe("Pagination offset."),
};
const obj = z.object(crawlContentsInputSchema);
export type CrawlContentsArgs = z.infer<typeof obj>;

export async function runCrawlContents(
  client: Pick<ScrapflyClient, "crawlContents">,
  args: CrawlContentsArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, ...opts } = args;
    const contents = await client.crawlContents(crawler_uuid, opts);
    return jsonResult(contents);
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCrawlContents(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "crawl_contents",
    {
      title: "Read Scrapfly crawl contents",
      description: "Fetch the stored content of crawled pages for a crawler_uuid. Default format markdown. Optionally filter to one url or paginate.",
      inputSchema: crawlContentsInputSchema,
    },
    async (args) => runCrawlContents(client, args as CrawlContentsArgs),
  );
}
```

- [ ] **Step 2: Add a focused test `crawl-contents.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { runCrawlContents } from "./crawl-contents.js";

describe("runCrawlContents", () => {
  it("strips crawler_uuid out of the options it forwards", async () => {
    const client = { crawlContents: vi.fn().mockResolvedValue({ contents: {}, links: [] }) };
    await runCrawlContents(client as never, { crawler_uuid: "abc", format: "markdown" });
    expect(client.crawlContents).toHaveBeenCalledWith("abc", { format: "markdown" });
  });
});
```

- [ ] **Step 3: Run test, verify PASS**

Run: `cd packages/crawl-server && npx vitest run src/tools/crawl-contents.test.ts`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/crawl-server/src/tools/crawl-contents.ts packages/crawl-server/src/tools/crawl-contents.test.ts
git commit -m "feat(crawl): add crawl_contents tool"
```

---

## Task 13: crawl-server — `list_crawled_urls` + `cancel_crawl` tools

**Files:**
- Create: `packages/crawl-server/src/tools/list-crawled-urls.ts`
- Create: `packages/crawl-server/src/tools/cancel-crawl.ts`

- [ ] **Step 1: Write `list-crawled-urls.ts`**

```ts
import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const listUrlsInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
  status: z.enum(["visited", "pending", "failed"]).optional().describe("Filter URLs by crawl status."),
  page: z.number().int().positive().optional().describe("1-based page number."),
  per_page: z.number().int().positive().optional().describe("Page size."),
};
const obj = z.object(listUrlsInputSchema);
export type ListUrlsArgs = z.infer<typeof obj>;

export async function runListCrawledUrls(
  client: Pick<ScrapflyClient, "crawlUrls">,
  args: ListUrlsArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, ...opts } = args;
    return jsonResult(await client.crawlUrls(crawler_uuid, opts));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerListCrawledUrls(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "list_crawled_urls",
    {
      title: "List Scrapfly crawled URLs",
      description: "List the URLs a crawl has visited/pending/failed, paginated.",
      inputSchema: listUrlsInputSchema,
    },
    async (args) => runListCrawledUrls(client, args as ListUrlsArgs),
  );
}
```

- [ ] **Step 2: Write `cancel-crawl.ts`**

```ts
import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const cancelCrawlInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
};
const obj = z.object(cancelCrawlInputSchema);
export type CancelCrawlArgs = z.infer<typeof obj>;

export async function runCancelCrawl(
  client: Pick<ScrapflyClient, "crawlCancel">,
  args: CancelCrawlArgs,
): Promise<ToolResult> {
  try {
    const cancelled = await client.crawlCancel(args.crawler_uuid);
    return jsonResult({ crawler_uuid: args.crawler_uuid, cancelled });
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCancelCrawl(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "cancel_crawl",
    {
      title: "Cancel a Scrapfly crawl",
      description: "Stop a running crawl by its crawler_uuid. Idempotent.",
      inputSchema: cancelCrawlInputSchema,
    },
    async (args) => runCancelCrawl(client, args as CancelCrawlArgs),
  );
}
```

- [ ] **Step 3: Add test `cancel-crawl.test.ts`**

```ts
import { describe, it, expect, vi } from "vitest";
import { runCancelCrawl } from "./cancel-crawl.js";

describe("runCancelCrawl", () => {
  it("calls crawlCancel and reports the boolean", async () => {
    const client = { crawlCancel: vi.fn().mockResolvedValue(true) };
    const res = await runCancelCrawl(client as never, { crawler_uuid: "abc" });
    expect(client.crawlCancel).toHaveBeenCalledWith("abc");
    expect(res.content[0].type === "text" && res.content[0].text).toContain('"cancelled": true');
  });
});
```

- [ ] **Step 4: Run test, verify PASS**

Run: `cd packages/crawl-server && npx vitest run src/tools/cancel-crawl.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/crawl-server/src/tools/list-crawled-urls.ts packages/crawl-server/src/tools/cancel-crawl.ts packages/crawl-server/src/tools/cancel-crawl.test.ts
git commit -m "feat(crawl): add list_crawled_urls and cancel_crawl tools"
```

---

## Task 14: crawl-server — server assembly + entry + build

**Files:**
- Create: `packages/crawl-server/src/server.ts`
- Create: `packages/crawl-server/src/index.ts`

- [ ] **Step 1: Write `packages/crawl-server/src/server.ts`**

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@scrapfly-mcp/core";
import type { ScrapflyClient } from "scrapfly-sdk";
import { registerStartCrawl } from "./tools/start-crawl.js";
import { registerCrawlStatus } from "./tools/crawl-status.js";
import { registerCrawlContents } from "./tools/crawl-contents.js";
import { registerListCrawledUrls } from "./tools/list-crawled-urls.js";
import { registerCancelCrawl } from "./tools/cancel-crawl.js";

export function createCrawlServer(client: ScrapflyClient = createClient()): McpServer {
  const server = new McpServer({ name: "scrapfly-crawl", version: "0.1.0" });
  registerStartCrawl(server, client);
  registerCrawlStatus(server, client);
  registerCrawlContents(server, client);
  registerListCrawledUrls(server, client);
  registerCancelCrawl(server, client);
  return server;
}
```

- [ ] **Step 2: Write `packages/crawl-server/src/index.ts`**

```ts
#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createCrawlServer } from "./server.js";

async function main(): Promise<void> {
  const server = createCrawlServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[scrapfly-crawl] running on stdio");
}

main().catch((error) => {
  console.error("[scrapfly-crawl] fatal:", error);
  process.exit(1);
});
```

- [ ] **Step 3: Build + smoke**

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm run build -w @scrapfly-mcp/crawl-server
SCRAPFLY_API_KEY=scp-live-dummy node packages/crawl-server/build/index.js <<< "" 2>&1 | head -1
```
Expected: build succeeds; prints `[scrapfly-crawl] running on stdio` to stderr.

- [ ] **Step 4: Commit**

```bash
git add packages/crawl-server/src/server.ts packages/crawl-server/src/index.ts
git commit -m "feat(crawl): assemble McpServer and stdio entrypoint"
```

---

## Task 15: Whole-repo build, typecheck, and full test run

- [ ] **Step 1: Clean build all packages in dependency order**

Run: `cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp && npm run clean && npm run build`
Expected: core → scrape-server → crawl-server all compile (TS project references order). No errors.

- [ ] **Step 2: Run all unit tests**

Run: `npm test`
Expected: all vitest suites pass across core, scrape-server, crawl-server.

- [ ] **Step 3: Commit any build-config fixes discovered**

```bash
git add -A
git commit -m "chore: green build + full unit test pass" || echo "nothing to commit"
```

---

## Task 16: Gated live integration smoke (costs ~1 credit)

**Files:**
- Create: `packages/scrape-server/src/tools/fetch-page.integration.test.ts`

- [ ] **Step 1: Write the gated integration test**

```ts
import { describe, it, expect } from "vitest";
import { createClient } from "@scrapfly-mcp/core";
import { runFetchPage } from "./fetch-page.js";

const RUN = process.env.SCRAPFLY_LIVE === "1" && !!process.env.SCRAPFLY_API_KEY;

describe.skipIf(!RUN)("fetch_page (live)", () => {
  it("scrapes example.com and returns 200 content", async () => {
    const res = await runFetchPage(createClient(), { url: "https://example.com", format: "text" });
    expect(res.isError).toBeUndefined();
    const text = res.content[0].type === "text" ? res.content[0].text : "";
    expect(text).toContain('"status_code": 200');
  }, 30000);
});
```

- [ ] **Step 2: Run it WITH the real key (recover key into the env just for this run)**

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp
KEY="$(python3 -c "import json;print(json.load(open('/home/kasey/.claude.json'))['mcpServers']['scrapfly-cloud-mcp']['url'].split('key=')[1])")"
SCRAPFLY_LIVE=1 SCRAPFLY_API_KEY="$KEY" npx vitest run -w @scrapfly-mcp/scrape-server src/tools/fetch-page.integration.test.ts
```
Expected: PASS — confirms the key works and the scrape path is correct end-to-end. (Redact the key from any pasted output.)

- [ ] **Step 3: Commit**

```bash
git add packages/scrape-server/src/tools/fetch-page.integration.test.ts
git commit -m "test(scrape): add gated live integration smoke for fetch_page"
```

---

## Task 17: Register both servers + update permissions + retire hosted entry

- [ ] **Step 1: Recover the key and register both servers at user scope**

Run:
```bash
KEY="$(python3 -c "import json;print(json.load(open('/home/kasey/.claude.json'))['mcpServers']['scrapfly-cloud-mcp']['url'].split('key=')[1])")"
BASE=/home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp/packages
claude mcp add --scope user --transport stdio --env SCRAPFLY_API_KEY="$KEY" scrapfly-scrape -- node "$BASE/scrape-server/build/index.js"
claude mcp add --scope user --transport stdio --env SCRAPFLY_API_KEY="$KEY" scrapfly-crawl  -- node "$BASE/crawl-server/build/index.js"
```
Expected: both added to the ACTIVE config (`/home/kasey/.claude/.claude.json`). Redact the key from any output.

- [ ] **Step 2: Verify the CLI sees them**

Run: `claude mcp get scrapfly-scrape 2>&1 | sed -E 's/(SCRAPFLY_API_KEY=)[^ ]+/\1REDACTED/'; claude mcp get scrapfly-crawl 2>&1 | sed -E 's/(SCRAPFLY_API_KEY=)[^ ]+/\1REDACTED/'`
Expected: both servers print their stdio command; no "not found".

- [ ] **Step 3: Update `~/.claude/settings.json` allow-list (retire hosted, allow the two new servers)**

Edit `/home/kasey/.claude/settings.json`: replace the line `"mcp__scrapfly-cloud-mcp__*",` in `permissions.allow` with:
```json
      "mcp__scrapfly-scrape__*",
      "mcp__scrapfly-crawl__*",
```
(Confirm `scrapfly-cloud-mcp` is NOT re-registered anywhere — the hosted entry stays retired.)

- [ ] **Step 4: No commit** (these edits are in `~/.claude`, outside the repo).

---

## Task 18: Live MCP test run (the original "give it a test run")

> MCP servers are loaded at session start, so the new tools are available **after restarting Claude Code**. This task is performed in a fresh session.

- [ ] **Step 1: In a new Claude session, confirm the tools load**

Run: `claude mcp list`
Expected: `scrapfly-scrape` and `scrapfly-crawl` both show `✔ Connected`.

- [ ] **Step 2: Exercise `account_info` (free)** — ask Claude to call `mcp__scrapfly-scrape__account_info`. Expected: JSON with `scrape_credits.remaining`.

- [ ] **Step 3: Exercise `fetch_page`** — call `mcp__scrapfly-scrape__fetch_page` with `{ "url": "https://example.com", "format": "markdown" }`. Expected: `status_code: 200`, markdown content.

- [ ] **Step 4: Exercise the crawl lifecycle (small + bounded)** — `start_crawl` with `{ "url": "https://example.com", "page_limit": 2 }`, then `crawl_status` until `is_finished`, then `crawl_contents`. Expected: a `crawler_uuid`, terminal status `DONE`, content for the crawled pages.

---

## Task 19: Consolidate `infrastructure/` into one GitHub repo (FINAL — gated)

> **Blocked on a user decision** (public vs private) and its own secret-scan mini-design. Do NOT push without explicit confirmation. Active profile MUST be `personal` → `kasey-purvor`.

- [ ] **Step 1: Confirm profile**

Run: `echo "profile=$CLOUD_PROFILE gh=$GH_CONFIG_DIR"`
Expected: `profile=personal` and `gh-personal`. If not, STOP and tell the user (per CLAUDE.md GitHub rule).

- [ ] **Step 2: Flatten the inner repo** — the build created `scrapfly-mcp/.git`. To make `infrastructure/` a single repo, remove the nested `.git` first (its commits are dev-only history):

Run: `rm -rf /home/kasey/dev_wsl/infrastructure/tools/scrapfly-mcp/.git`

- [ ] **Step 3: Secret scan + root `.gitignore`** — write `/home/kasey/dev_wsl/infrastructure/.gitignore` excluding `node_modules/`, `build/`, `dist/`, `**/.env`, `*.key`, `*.pem`, `__pycache__/`, `.venv/`, `*.tsbuildinfo`, `htmlcov/`. Then scan for stray secrets BEFORE any `git add`:

Run: `grep -rIl --exclude-dir=node_modules -E 'scp-live-|SCRAPFLY_API_KEY=|api[_-]?key' /home/kasey/dev_wsl/infrastructure | head`
Expected: review each hit; ensure no real key is about to be committed. (Keys live in `~/.claude`, not the repo — confirm.)

- [ ] **Step 4: ASK the user — public or private?** Use AskUserQuestion. Do not proceed until answered.

- [ ] **Step 5: Init, commit, create remote, push** (after confirmation):

Run:
```bash
cd /home/kasey/dev_wsl/infrastructure
git init && git add -A
git -c user.name="$(git config --global user.name)" -c user.email="$(git config --global user.email)" commit -m "chore: initial commit of infrastructure tools and services"
gh repo create infrastructure --<public|private> --source=. --remote=origin --push
```
Expected: repo created under `kasey-purvor`, code pushed. (No Claude attribution in the commit.)

---

## Self-Review

**1. Spec coverage:**
- §3 decisions (TS, monorepo, verb naming, fetch_page+account_info+screenshot, retire hosted, env key, stdio) → Tasks 1, 6–9 (scrape tools), 17 (retire + register). ✓
- §5 scrape tool options → Task 6 `fetchPageInputSchema` (all common+advanced options present). ✓
- §5 account_info / take_screenshot → Tasks 7, 8. ✓
- §6 crawl tools (start/status/contents/list/cancel) → Tasks 10–13. ✓
- §6 no-blocking-poll → enforced by using low-level `client.crawl*` single-call methods (not `Crawl.wait()`); documented in `start_crawl` description. ✓
- §7 key handling → Task 2 (loadApiKey) + Task 17 (env injection). ✓
- §7 error handling → Task 4 (describeError) + `errorResult` used in every tool. ✓
- §7 registration → Task 17. ✓
- §7 testing (unit + gated integration) → Tasks 2–14 unit, Task 16 gated. ✓
- §8 one-repo relationship → Task 19 (flatten inner .git). ✓
- §9 risks → resolved by research; crawler in SDK (no REST), screenshot via `client.screenshot`, MCP `registerTool`. ✓

**2. Placeholder scan:** No "TBD/TODO/handle errors appropriately". Every code step has complete code. `--<public|private>` in Task 19 Step 5 is an intentional branch resolved by Step 4's answer, not a placeholder. ✓

**3. Type consistency:** `ToolResult` defined in core/mcp.ts, used everywhere. `run*` handlers accept `Pick<ScrapflyClient, 'method'>` and are called with the same names in tests and `register*`. Distil helpers match the verified `.d.ts` access paths (`result.result.*`, `result.context.cost.total`, `state.urls_*`). Tool ids (`fetch_page`, `account_info`, `take_screenshot`, `start_crawl`, `crawl_status`, `crawl_contents`, `list_crawled_urls`, `cancel_crawl`) are consistent between `register*` and Task 18. ✓

**Verify-at-execution notes:**
- The exact `ConstructorParameters<typeof ScrapeConfig>[0]` option object is accepted by the SDK; if the SDK's constructor typing is stricter than `Record<string, unknown>`, the `as` cast in `build*Options` bridges it (validated by Task 16 live run).
- Confirm `client.crawlContents`/`crawlUrls`/`crawlCancel` method names against `node_modules/scrapfly-sdk` `.d.ts` during Task 10–13 (research reported them from the installed 0.11.0 types).
