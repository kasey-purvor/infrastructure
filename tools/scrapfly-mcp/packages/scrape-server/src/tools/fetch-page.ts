import { z } from "zod";
import { ScrapeConfig, type ScrapflyClient, type ScrapeResult } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { jsonResult, errorResult, proxyCacheShape, type ToolResult } from "@scrapfly-mcp/core";

export const fetchPageInputSchema = {
  url: z.string().url().describe("Absolute URL of the page to scrape."),
  render_js: z
    .boolean()
    .optional()
    .describe("Render in a real headless browser (enables JS, scrolling, waits)."),
  ...proxyCacheShape,
  auto_scroll: z
    .boolean()
    .optional()
    .describe("Scroll to page bottom before capture (requires render_js)."),
  rendering_wait: z
    .number()
    .int()
    .nonnegative()
    .optional()
    .describe("Extra ms to wait after load (requires render_js)."),
  wait_for_selector: z
    .string()
    .optional()
    .describe("CSS selector to wait for before reading (requires render_js)."),
  method: z.enum(["GET", "POST", "PUT", "PATCH", "HEAD"]).optional().describe("Upstream HTTP method."),
  headers: z.record(z.string()).optional().describe("Custom request headers."),
  body: z.string().optional().describe("Raw request body for POST/PUT."),
  js_scenario: z
    .record(z.any())
    .optional()
    .describe("Declarative browser automation steps (requires render_js)."),
  geolocation: z.string().optional().describe("Spoof geolocation as 'lat,lng'."),
  format: z
    .enum(["json", "text", "markdown", "clean_html", "raw"])
    .optional()
    .describe("Output content format."),
  cost_budget: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Max API credits allowed for this scrape."),
};

const inputObject = z.object(fetchPageInputSchema);
export type FetchPageArgs = z.infer<typeof inputObject>;

/** Pure: map validated args to ScrapeConfig constructor options. */
export function buildScrapeOptions(args: FetchPageArgs): ConstructorParameters<typeof ScrapeConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url, raise_on_upstream_error: true };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  return opts as ConstructorParameters<typeof ScrapeConfig>[0];
}

/** Pure: distil a ScrapeResult into the compact response. */
export function distillScrape(result: ScrapeResult) {
  return {
    url: result.result.url,
    content: result.result.content,
    status_code: result.result.status_code,
    from_cache: result.context.cache?.state === "HIT",
    credits_used: result.context.cost?.total,
    log_url: result.result.log_url,
  };
}

/** Injectable handler: testable with a fake client. */
export async function runFetchPage(
  client: Pick<ScrapflyClient, "scrape">,
  args: FetchPageArgs,
): Promise<ToolResult> {
  try {
    const result = (await client.scrape(new ScrapeConfig(buildScrapeOptions(args)))) as ScrapeResult;
    return jsonResult(distillScrape(result));
  } catch (err) {
    return errorResult(err);
  }
}

export function registerFetchPage(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "fetch_page",
    {
      title: "Fetch a web page (Scrapfly scrape)",
      description:
        "Scrape ONE page and return its content. Use render_js for JS-heavy sites, asp to bypass anti-bot, " +
        "format='markdown' for clean text. Synchronous — returns the page in one call.",
      inputSchema: fetchPageInputSchema,
    },
    async (args) => runFetchPage(client, args as FetchPageArgs),
  );
}
