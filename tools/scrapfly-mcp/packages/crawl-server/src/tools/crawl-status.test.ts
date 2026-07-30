import { describe, it, expect, vi } from "vitest";
import { distillStatus, runCrawlStatus } from "./crawl-status.js";

const fakeStatus = {
  crawler_uuid: "abc",
  status: "RUNNING",
  is_finished: false,
  is_success: null,
  state: {
    urls_visited: 5,
    urls_extracted: 4,
    urls_failed: 1,
    urls_skipped: 0,
    urls_to_crawl: 12,
    api_credit_used: 30,
    duration: 9,
    stop_reason: null,
  },
};

describe("distillStatus", () => {
  it("flattens status + state metrics", () => {
    expect(distillStatus(fakeStatus as never)).toEqual({
      crawler_uuid: "abc",
      status: "RUNNING",
      is_finished: false,
      is_success: null,
      urls_visited: 5,
      urls_extracted: 4,
      urls_failed: 1,
      urls_skipped: 0,
      urls_to_crawl: 12,
      api_credit_used: 30,
      duration: 9,
      stop_reason: null,
    });
  });
});

describe("runCrawlStatus", () => {
  it("calls client.crawlStatus with the uuid", async () => {
    const client = { crawlStatus: vi.fn().mockResolvedValue(fakeStatus) };
    const res = await runCrawlStatus(client as never, { crawler_uuid: "abc" });
    expect(client.crawlStatus).toHaveBeenCalledWith("abc");
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain('"urls_visited": 5');
  });
});
