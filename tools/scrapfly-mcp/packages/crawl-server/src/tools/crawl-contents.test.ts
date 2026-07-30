import { describe, it, expect, vi } from "vitest";
import { runCrawlContents } from "./crawl-contents.js";

describe("runCrawlContents", () => {
  it("strips crawler_uuid out of the options it forwards", async () => {
    const client = { crawlContents: vi.fn().mockResolvedValue({ contents: {}, links: [] }) };
    await runCrawlContents(client as never, { crawler_uuid: "abc", format: "markdown" });
    expect(client.crawlContents).toHaveBeenCalledWith("abc", { format: "markdown" });
  });
});
