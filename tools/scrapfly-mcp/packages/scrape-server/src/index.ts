#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createScrapeServer } from "./server.js";

async function main(): Promise<void> {
  const server = createScrapeServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stdout is the JSON-RPC channel — log only to stderr.
  console.error("[scrapfly-scrape] running on stdio");
}

main().catch((error) => {
  console.error("[scrapfly-scrape] fatal:", error);
  process.exit(1);
});
