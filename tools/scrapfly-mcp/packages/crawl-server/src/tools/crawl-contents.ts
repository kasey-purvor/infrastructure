import { z } from "zod";
import type { ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, type ToolResult } from "@scrapfly-mcp/core";

const CONTENT_FORMATS = [
  "html",
  "clean_html",
  "markdown",
  "text",
  "json",
  "extracted_data",
  "page_metadata",
] as const;

export const crawlContentsInputSchema = {
  crawler_uuid: z.string().describe("UUID returned by start_crawl."),
  format: z
    .enum(CONTENT_FORMATS)
    .default("markdown")
    .describe("Content representation to return (default markdown)."),
  url: z.string().url().optional().describe("If given, return only this crawled URL's content."),
  limit: z.number().int().positive().optional().describe("Max number of pages to return."),
  offset: z.number().int().nonnegative().optional().describe("Pagination offset."),
};
const obj = z.object(crawlContentsInputSchema);
export type CrawlContentsArgs = z.infer<typeof obj>;

export async function runCrawlContents(
  client: Pick<ScrapflyClient, "crawlContents">,
  args: CrawlContentsArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, ...opts } = args;
    const contents = await client.crawlContents(crawler_uuid, opts);
    return jsonResult(contents);
  } catch (err) {
    return errorResult(err);
  }
}

export function registerCrawlContents(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "crawl_contents",
    {
      title: "Read Scrapfly crawl contents",
      description:
        "Fetch the stored content of crawled pages for a crawler_uuid. Default format markdown. Optionally filter to one url or paginate.",
      inputSchema: crawlContentsInputSchema,
    },
    async (args) => runCrawlContents(client, args as CrawlContentsArgs),
  );
}
