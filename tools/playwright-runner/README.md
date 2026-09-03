# playwright-runner

Shared Playwright install for **parallel headless browser automation** by Claude Code
agents. The Playwright MCP plugin holds a single profile lock, so only one agent can
browse at a time; this runner sidesteps that — every script launches its own headless
Chromium, so parallelism is limited only by the machine.

## ⚠️ Version pin — do not upgrade blindly

`playwright` is pinned to **exactly 1.61.0** (Chromium build 1228). Playwright 1.62.x
ships Chromium build 1234 (Chrome for Testing 151.0.7922.34), whose **headless
screenshot capture hangs forever on this machine** (WSL2, kernel
5.15.167.4-microsoft): navigation and JS evaluation work, but the compositor never
produces a frame, so `page.screenshot()` and even raw CDP `Page.captureScreenshot`
time out. Verified 2026-08-19: builds 1179/1217/1228 all screenshot fine; 1234 hangs
in both full-Chrome headless and chrome-headless-shell, with and without
`--disable-gpu` / `--no-sandbox`.

Before upgrading, re-test: `node parallel-smoke.mjs 3 /tmp` — three SHA lines means
screenshots work.

Escape hatch if stuck on 1.62/build 1234 (independently verified by a second agent,
2026-08-19): launch with
`args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--use-gl=swiftshader', '--disable-software-rasterizer', '--run-all-compositor-stages-before-draw']`
makes screenshots work on the otherwise-hanging build. The pin remains the cleaner fix.

## Usage from an agent

Write your script anywhere (e.g. your scratchpad) and import Playwright by absolute
path — ESM resolves imports relative to the *script*, not the cwd:

```js
// my-task.mjs
import { chromium } from '/home/kasey/dev_wsl/infrastructure/tools/playwright-runner/node_modules/playwright/index.mjs';

const browser = await chromium.launch();          // headless, own process — no lock
const page = await browser.newPage();
await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });
await page.screenshot({ path: 'out.png', fullPage: true });
await browser.close();
```

Run with `node my-task.mjs`. Scripts placed inside this directory can use the plain
`import { chromium } from 'playwright'` form instead.

### Reusing a login across scripts

Log in once, save state, reuse it — avoids re-typing credentials per script:

```js
await context.storageState({ path: '/path/to/state.json' });      // after login
const context = await browser.newContext({ storageState: '/path/to/state.json' });
```

Treat the state file as a credential: keep it in a scratchpad or `~/.secrets`,
mode 600, delete when done.

## Files

- `parallel-smoke.mjs` — health check: N parallel browsers → prod SHA + screenshot each.
