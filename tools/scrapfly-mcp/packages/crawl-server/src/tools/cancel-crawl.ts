import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const cancelCrawlInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
};
const obj = z.object(cancelCrawlInputSchema);
export type CancelCrawlArgs = z.infer<typeof obj>;

export async function runCancelCrawl(
  client: Pick<ScrapflyClient, "crawlCancel">,
  args: CancelCrawlArgs,
): Promise<ToolResult> {
  try {
    const cancelled = await client.crawlCancel(args.crawler_uuid);
    return jsonResult({ crawler_uuid: args.crawler_uuid, cancelled });
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCancelCrawl(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "cancel_crawl",
    {
      title: "Cancel a Scrapfly crawl",
      description: "Stop a running crawl by its crawler_uuid. Idempotent.",
      inputSchema: cancelCrawlInputSchema,
    },
    async (args) => runCancelCrawl(client, args as CancelCrawlArgs),
  );
}
