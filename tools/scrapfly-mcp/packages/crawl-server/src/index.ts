#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createCrawlServer } from "./server.js";

async function main(): Promise<void> {
  const server = createCrawlServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stdout is the JSON-RPC channel — log only to stderr.
  console.error("[scrapfly-crawl] running on stdio");
}

main().catch((error) => {
  console.error("[scrapfly-crawl] fatal:", error);
  process.exit(1);
});
