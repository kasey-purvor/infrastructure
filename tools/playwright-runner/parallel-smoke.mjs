// Smoke test: N fully independent headless Chromium instances in parallel.
// Usage: node parallel-smoke.mjs [count] [outDir]
import { chromium } from 'playwright';

const count = Number(process.argv[2] ?? 3);
const outDir = process.argv[3] ?? '/tmp';
const url = 'https://mydams-v2.vercel.app';

const run = async (i) => {
  const t0 = Date.now();
  const browser = await chromium.launch(); // headless, own process, no shared profile
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle' });
  const sha = await page.evaluate(() => document.documentElement.dataset.mydamsGitCommitSha);
  await page.screenshot({ path: `${outDir}/smoke-${i}.png` });
  await browser.close();
  return { i, sha, ms: Date.now() - t0 };
};

const results = await Promise.all(Array.from({ length: count }, (_, i) => run(i)));
for (const r of results) console.log(`browser ${r.i}: sha=${r.sha} in ${r.ms}ms`);
