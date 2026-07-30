import { z } from "zod";

/** Proxy + cache options shared by scrape, screenshot, and crawl tools. */
export const proxyCacheShape = {
  asp: z
    .boolean()
    .optional()
    .describe("Enable Scrapfly Anti-Scraping Protection (anti-bot bypass)."),
  country: z
    .string()
    .length(2)
    .optional()
    .describe("ISO 3166 country code for the proxy, e.g. 'us', 'gb'."),
  cache: z.boolean().optional().describe("Serve from Scrapfly cache when a fresh entry exists."),
  cache_ttl: z.number().int().positive().optional().describe("Cache time-to-live in seconds."),
};
