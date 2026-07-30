import { z } from "zod";
import { CrawlerConfig, type ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, proxyCacheShape, type ToolResult } from "@scrapfly-mcp/core";

const CONTENT_FORMATS = [
  "html",
  "clean_html",
  "markdown",
  "text",
  "json",
  "extracted_data",
  "page_metadata",
] as const;

export const startCrawlInputSchema = {
  url: z.string().url().describe("Seed URL to start crawling from."),
  page_limit: z.number().int().positive().optional().describe("Max number of pages to crawl."),
  max_depth: z.number().int().nonnegative().optional().describe("Max link depth from the seed."),
  max_duration: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Max crawl wall-clock duration in seconds."),
  max_api_credit: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Max API credits the crawl may consume."),
  max_concurrency: z.number().int().positive().optional().describe("Max concurrent fetches."),
  content_formats: z
    .array(z.enum(CONTENT_FORMATS))
    .optional()
    .describe("Content representations to store per page."),
  include_only_paths: z
    .array(z.string())
    .optional()
    .describe("Restrict crawl to these URL path patterns."),
  exclude_paths: z.array(z.string()).optional().describe("URL path patterns to exclude."),
  ignore_base_path_restriction: z
    .boolean()
    .optional()
    .describe("Allow crawling outside the seed's base path."),
  follow_internal_subdomains: z
    .boolean()
    .optional()
    .describe("Follow links into subdomains of the seed domain."),
  respect_robots_txt: z.boolean().optional().describe("Honor robots.txt (server default true)."),
  use_sitemaps: z.boolean().optional().describe("Seed the crawl from the site's sitemaps."),
  ignore_no_follow: z.boolean().optional().describe("Follow rel=nofollow links anyway."),
  delay: z.number().int().nonnegative().optional().describe("Delay between requests."),
  rendering_delay: z
    .number()
    .int()
    .nonnegative()
    .optional()
    .describe("Delay after render before reading."),
  proxy_pool: z.string().optional().describe("Proxy pool name for the crawl."),
  ...proxyCacheShape,
};

const crawlObject = z.object(startCrawlInputSchema);
export type StartCrawlArgs = z.infer<typeof crawlObject>;

export function buildCrawlOptions(args: StartCrawlArgs): ConstructorParameters<typeof CrawlerConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  // Scrapfly only stores the content representations requested at crawl time. Default to
  // markdown so the common "crawl then crawl_contents(format='markdown')" path returns text
  // without the caller having to know about the coupling. Explicit content_formats wins.
  if (opts.content_formats === undefined) opts.content_formats = ["markdown"];
  return opts as ConstructorParameters<typeof CrawlerConfig>[0];
}

export async function runStartCrawl(
  client: Pick<ScrapflyClient, "crawl">,
  args: StartCrawlArgs,
): Promise<ToolResult> {
  try {
    const { crawler_uuid, status } = await client.crawl(new CrawlerConfig(buildCrawlOptions(args)));
    return jsonResult({ crawler_uuid, status });
  } catch (err) {
    return errorResult(err);
  }
}

export function registerStartCrawl(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "start_crawl",
    {
      title: "Start a Scrapfly crawl",
      description:
        "Begin an ASYNC crawl from a seed URL and return a crawler_uuid immediately. " +
        "Then poll crawl_status with that uuid until is_finished is true; fetch pages with crawl_contents. " +
        "Defaults to storing markdown content; set content_formats to store other representations " +
        "(crawl_contents can only return formats stored at crawl time).",
      inputSchema: startCrawlInputSchema,
    },
    async (args) => runStartCrawl(client, args as StartCrawlArgs),
  );
}
