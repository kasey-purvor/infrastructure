import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@scrapfly-mcp/core";
import type { ScrapflyClient } from "scrapfly-sdk";
import { registerStartCrawl } from "./tools/start-crawl.js";
import { registerCrawlStatus } from "./tools/crawl-status.js";
import { registerCrawlContents } from "./tools/crawl-contents.js";
import { registerListCrawledUrls } from "./tools/list-crawled-urls.js";
import { registerCancelCrawl } from "./tools/cancel-crawl.js";

export function createCrawlServer(client: ScrapflyClient = createClient()): McpServer {
  const server = new McpServer({ name: "scrapfly-crawl", version: "0.1.0" });
  registerStartCrawl(server, client);
  registerCrawlStatus(server, client);
  registerCrawlContents(server, client);
  registerListCrawledUrls(server, client);
  registerCancelCrawl(server, client);
  return server;
}
