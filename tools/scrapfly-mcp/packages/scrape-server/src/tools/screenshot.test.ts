import { describe, it, expect, vi } from "vitest";
import { buildShotOptions, mimeForFormat, runScreenshot } from "./screenshot.js";

describe("buildShotOptions", () => {
  it("passes url + capture through, omits undefined", () => {
    const o = buildShotOptions({ url: "https://x.com", capture: "fullpage" }) as Record<string, unknown>;
    expect(o).toEqual({ url: "https://x.com", capture: "fullpage" });
  });
});

describe("mimeForFormat", () => {
  it("maps formats to mime types, defaulting to jpeg", () => {
    expect(mimeForFormat("png")).toBe("image/png");
    expect(mimeForFormat(undefined)).toBe("image/jpeg");
  });
});

describe("runScreenshot", () => {
  it("returns an image content block with base64 data", async () => {
    const bytes = new Uint8Array([1, 2, 3]).buffer;
    const client = {
      screenshot: vi.fn().mockResolvedValue({ image: bytes, metadata: { extension_name: "png" } }),
    };
    const res = await runScreenshot(client as never, { url: "https://x.com", format: "png" });
    expect(client.screenshot).toHaveBeenCalledOnce();
    const block = res.content[0];
    expect(block).toMatchObject({ type: "image", mimeType: "image/png" });
    expect(block.type === "image" && block.data).toBe(Buffer.from(bytes).toString("base64"));
  });

  it("returns an error result when the client throws", async () => {
    const client = { screenshot: vi.fn().mockRejectedValue(new Error("nope")) };
    const res = await runScreenshot(client as never, { url: "https://x.com" });
    expect(res.isError).toBe(true);
  });
});
