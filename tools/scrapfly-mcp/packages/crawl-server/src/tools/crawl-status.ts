import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const crawlStatusInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
};
const obj = z.object(crawlStatusInputSchema);
export type CrawlStatusArgs = z.infer<typeof obj>;

type CrawlerStatus = Awaited<ReturnType<ScrapflyClient["crawlStatus"]>>;

export function distillStatus(s: CrawlerStatus) {
  return {
    crawler_uuid: s.crawler_uuid,
    status: s.status,
    is_finished: s.is_finished,
    is_success: s.is_success,
    urls_visited: s.state.urls_visited,
    urls_extracted: s.state.urls_extracted,
    urls_failed: s.state.urls_failed,
    urls_skipped: s.state.urls_skipped,
    urls_to_crawl: s.state.urls_to_crawl,
    api_credit_used: s.state.api_credit_used,
    duration: s.state.duration,
    stop_reason: s.state.stop_reason,
  };
}

export async function runCrawlStatus(
  client: Pick<ScrapflyClient, "crawlStatus">,
  args: CrawlStatusArgs,
): Promise<ToolResult> {
  try {
    return jsonResult(distillStatus(await client.crawlStatus(args.crawler_uuid)));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCrawlStatus(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "crawl_status",
    {
      title: "Check Scrapfly crawl status",
      description:
        "Return progress for a crawler_uuid. Poll this until is_finished is true (status 'DONE'); is_success tells you if it succeeded.",
      inputSchema: crawlStatusInputSchema,
    },
    async (args) => runCrawlStatus(client, args as CrawlStatusArgs),
  );
}
