import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@scrapfly-mcp/core";
import type { ScrapflyClient } from "scrapfly-sdk";
import { registerFetchPage } from "./tools/fetch-page.js";
import { registerAccountInfo } from "./tools/account-info.js";
import { registerScreenshot } from "./tools/screenshot.js";

/** Build the scrape MCP server. Inject a client for tests; defaults to env-configured. */
export function createScrapeServer(client: ScrapflyClient = createClient()): McpServer {
  const server = new McpServer({ name: "scrapfly-scrape", version: "0.1.0" });
  registerFetchPage(server, client);
  registerAccountInfo(server, client);
  registerScreenshot(server, client);
  return server;
}
