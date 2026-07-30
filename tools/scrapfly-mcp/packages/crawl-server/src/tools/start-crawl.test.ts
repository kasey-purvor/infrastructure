import { describe, it, expect, vi } from "vitest";
import { buildCrawlOptions, runStartCrawl } from "./start-crawl.js";

describe("buildCrawlOptions", () => {
  it("requires url and forwards crawl options, omitting undefined", () => {
    const o = buildCrawlOptions({ url: "https://x.com", page_limit: 10, asp: true }) as Record<
      string,
      unknown
    >;
    expect(o).toMatchObject({ url: "https://x.com", page_limit: 10, asp: true });
    expect("country" in o).toBe(false);
  });

  it("defaults content_formats to ['markdown'] when not provided", () => {
    const o = buildCrawlOptions({ url: "https://x.com" }) as Record<string, unknown>;
    expect(o.content_formats).toEqual(["markdown"]);
  });

  it("respects an explicit content_formats over the default", () => {
    const o = buildCrawlOptions({ url: "https://x.com", content_formats: ["text"] }) as Record<
      string,
      unknown
    >;
    expect(o.content_formats).toEqual(["text"]);
  });
});

describe("runStartCrawl", () => {
  it("calls client.crawl and returns the uuid + status", async () => {
    const client = { crawl: vi.fn().mockResolvedValue({ crawler_uuid: "abc", status: "PENDING" }) };
    const res = await runStartCrawl(client as never, { url: "https://x.com" });
    expect(client.crawl).toHaveBeenCalledOnce();
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain('"crawler_uuid": "abc"');
  });

  it("returns an error result when the client throws", async () => {
    const client = { crawl: vi.fn().mockRejectedValue(new Error("bad config")) };
    const res = await runStartCrawl(client as never, { url: "https://x.com" });
    expect(res.isError).toBe(true);
  });
});
