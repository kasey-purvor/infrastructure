/** Reads the Scrapfly API key from an environment map. Defaults to process.env. */
export function loadApiKey(env: Record<string, string | undefined> = process.env): string {
  const key = env.SCRAPFLY_API_KEY;
  if (typeof key !== "string" || key.trim() === "") {
    throw new Error(
      "SCRAPFLY_API_KEY environment variable is not set. " +
        "Provide it via the MCP server's env block in your Claude config.",
    );
  }
  return key;
}
