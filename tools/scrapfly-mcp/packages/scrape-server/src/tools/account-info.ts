import type { ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

type AccountData = Awaited<ReturnType<ScrapflyClient["account"]>>;

export function distillAccount(acct: AccountData) {
  const s = acct.subscription;
  const u = s.usage.scrape;
  return {
    plan: s.plan_name,
    period: { start: s.period.start, end: s.period.end },
    scrape_credits: { remaining: u.remaining, limit: u.limit, current: u.current, extra: u.extra },
    concurrency: {
      remaining: u.concurrent_remaining,
      limit: u.concurrent_limit,
      in_use: u.concurrent_usage,
    },
    quota_reached: acct.project.quota_reached,
  };
}

export async function runAccountInfo(client: Pick<ScrapflyClient, "account">): Promise<ToolResult> {
  try {
    return jsonResult(distillAccount(await client.account()));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerAccountInfo(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "account_info",
    {
      title: "Scrapfly account / credit status",
      description:
        "Return remaining scrape credits, concurrency, plan, and billing period. Free — costs no credits.",
      inputSchema: {},
    },
    async () => runAccountInfo(client),
  );
}
