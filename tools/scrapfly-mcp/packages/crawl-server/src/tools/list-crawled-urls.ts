import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const listUrlsInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
  status: z
    .enum(["visited", "pending", "failed"])
    .optional()
    .describe("Filter URLs by crawl status."),
  page: z.number().int().positive().optional().describe("1-based page number."),
  per_page: z.number().int().positive().optional().describe("Page size."),
};
const obj = z.object(listUrlsInputSchema);
export type ListUrlsArgs = z.infer<typeof obj>;

export async function runListCrawledUrls(
  client: Pick<ScrapflyClient, "crawlUrls">,
  args: ListUrlsArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, ...opts } = args;
    return jsonResult(await client.crawlUrls(crawler_uuid, opts));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerListCrawledUrls(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "list_crawled_urls",
    {
      title: "List Scrapfly crawled URLs",
      description: "List the URLs a crawl has visited/pending/failed, paginated.",
      inputSchema: listUrlsInputSchema,
    },
    async (args) => runListCrawledUrls(client, args as ListUrlsArgs),
  );
}
