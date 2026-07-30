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
