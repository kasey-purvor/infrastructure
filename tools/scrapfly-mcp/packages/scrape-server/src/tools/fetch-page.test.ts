import { describe, it, expect, vi } from "vitest";
import { buildScrapeOptions, distillScrape, runFetchPage } from "./fetch-page.js";

describe("buildScrapeOptions", () => {
  it("passes the url through and always sets raise_on_upstream_error", () => {
    const opts = buildScrapeOptions({ url: "https://example.com" }) as Record<string, unknown>;
    expect(opts.url).toBe("https://example.com");
    expect(opts.raise_on_upstream_error).toBe(true);
  });

  it("forwards provided options verbatim and omits undefined ones", () => {
    const opts = buildScrapeOptions({ url: "https://x.com", render_js: true, country: "us" }) as Record<
      string,
      unknown
    >;
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
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain('"from_cache": false');
  });

  it("returns an error result (not a throw) when the client throws", async () => {
    const client = { scrape: vi.fn().mockRejectedValue(new Error("blocked")) };
    const res = await runFetchPage(client as never, { url: "https://example.com" });
    expect(res.isError).toBe(true);
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain("blocked");
  });
});
