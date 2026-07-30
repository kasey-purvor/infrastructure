import { describe, it, expect, vi } from "vitest";
import { distillAccount, runAccountInfo } from "./account-info.js";

const fakeAccount = {
  subscription: {
    plan_name: "Pro",
    period: { start: "2026-06-01", end: "2026-07-01" },
    usage: {
      scrape: {
        current: 100,
        limit: 1000,
        remaining: 900,
        extra: 0,
        concurrent_limit: 20,
        concurrent_remaining: 20,
        concurrent_usage: 0,
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
    const block = res.content[0];
    expect(block.type === "text" && block.text).toContain('"remaining": 900');
  });
});
