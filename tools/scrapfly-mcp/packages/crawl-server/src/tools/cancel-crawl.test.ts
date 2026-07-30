import { describe, it, expect, vi } from "vitest";
import { runCancelCrawl } from "./cancel-crawl.js";

describe("runCancelCrawl", () => {
  it("calls crawlCancel and reports the boolean", async () => {
    const client = { crawlCancel: vi.fn().mockResolvedValue(true) };
    const res = await runCancelCrawl(client as never, { crawler_uuid: "abc" });
    expect(client.crawlCancel).toHaveBeenCalledWith("abc");
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain('"cancelled": true');
  });
});
