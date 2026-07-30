import { z } from "zod";
import { ScreenshotConfig, type ScrapflyClient } from "scrapfly-sdk";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { errorResult, type ToolResult } from "@scrapfly-mcp/core";

export const screenshotInputSchema = {
  url: z.string().url().describe("Absolute URL of the page to screenshot."),
  format: z.enum(["jpg", "png", "webp", "gif"]).optional().describe("Image format (default jpg)."),
  capture: z
    .string()
    .optional()
    .describe("Capture area: 'fullpage', 'viewport', or a CSS selector."),
  resolution: z
    .string()
    .optional()
    .describe("Viewport resolution as 'WIDTHxHEIGHT', e.g. '1920x1080'."),
  country: z.string().length(2).optional().describe("ISO country code for the rendering proxy."),
  rendering_wait: z
    .number()
    .int()
    .nonnegative()
    .optional()
    .describe("Extra ms to wait after load before capture."),
  wait_for_selector: z.string().optional().describe("CSS selector to wait for before capture."),
  auto_scroll: z.boolean().optional().describe("Scroll to the bottom before capturing."),
};

const shotObject = z.object(screenshotInputSchema);
export type ScreenshotArgs = z.infer<typeof shotObject>;

export function buildShotOptions(args: ScreenshotArgs): ConstructorParameters<typeof ScreenshotConfig>[0] {
  const opts: Record<string, unknown> = { url: args.url };
  for (const [k, v] of Object.entries(args)) {
    if (k !== "url" && v !== undefined) opts[k] = v;
  }
  return opts as ConstructorParameters<typeof ScreenshotConfig>[0];
}

export function mimeForFormat(format: ScreenshotArgs["format"]): string {
  switch (format) {
    case "png":
      return "image/png";
    case "webp":
      return "image/webp";
    case "gif":
      return "image/gif";
    default:
      return "image/jpeg";
  }
}

export async function runScreenshot(
  client: Pick<ScrapflyClient, "screenshot">,
  args: ScreenshotArgs,
): Promise<ToolResult> {
  try {
    const shot = await client.screenshot(new ScreenshotConfig(buildShotOptions(args)));
    const data = Buffer.from(shot.image).toString("base64");
    return { content: [{ type: "image", data, mimeType: mimeForFormat(args.format) }] };
  } catch (err) {
    return errorResult(err);
  }
}

export function registerScreenshot(server: McpServer, client: ScrapflyClient): void {
  server.registerTool(
    "take_screenshot",
    {
      title: "Screenshot a web page (Scrapfly)",
      description:
        "Capture a PNG/JPG screenshot of a page. Use capture='fullpage' for the whole page or a CSS selector for one element.",
      inputSchema: screenshotInputSchema,
    },
    async (args) => runScreenshot(client, args as ScreenshotArgs),
  );
}
