import { ScrapflyClient } from "scrapfly-sdk";
import { loadApiKey } from "./config.js";

/**
 * Create a shared ScrapflyClient. One instance is safe across concurrent calls.
 * Pass an explicit key for tests; otherwise it is read from SCRAPFLY_API_KEY.
 */
export function createClient(apiKey: string = loadApiKey()): ScrapflyClient {
  return new ScrapflyClient({ key: apiKey });
}
