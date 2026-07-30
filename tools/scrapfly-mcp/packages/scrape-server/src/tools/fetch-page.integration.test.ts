import { describe, it, expect } from "vitest";
import { createClient } from "@scrapfly-mcp/core";
import { runFetchPage } from "./fetch-page.js";

// Gated: only runs with SCRAPFLY_LIVE=1 and a real SCRAPFLY_API_KEY (costs ~1 credit).
const RUN = process.env.SCRAPFLY_LIVE === "1" && !!process.env.SCRAPFLY_API_KEY;

describe.skipIf(!RUN)("fetch_page (live)", () => {
  it("scrapes example.com and returns 200 content", async () => {
    const res = await runFetchPage(createClient(), { url: "https://example.com", format: "text" });
    expect(res.isError).toBeUndefined();
    const block = res.content[0];
    const text = block.type === "text" ? block.text : "";
    expect(text).toContain('"status_code": 200');
  }, 30000);
});
