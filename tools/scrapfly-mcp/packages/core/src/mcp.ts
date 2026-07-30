import { describeError } from "./errors.js";

/**
 * Minimal shape of an MCP tool result (subset of CallToolResult we produce).
 * The `[key: string]: unknown` index signature makes this assignable to the
 * SDK's CallToolResult, which carries one for protocol passthrough fields.
 */
export interface ToolResult {
  content: Array<
    { type: "text"; text: string } | { type: "image"; data: string; mimeType: string }
  >;
  isError?: boolean;
  [key: string]: unknown;
}

/** Pretty-printed JSON as a text result. */
export function jsonResult(value: unknown): ToolResult {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}

/** Plain text result. */
export function textResult(text: string): ToolResult {
  return { content: [{ type: "text", text }] };
}

/** Error result: returned (not thrown) so the model sees the failure as tool output. */
export function errorResult(err: unknown): ToolResult {
  const { message, retryable, code } = describeError(err);
  const prefix = code ? `[${code}] ` : "";
  const suffix = retryable ? " (retryable: you may try again)" : "";
  return { content: [{ type: "text", text: `${prefix}${message}${suffix}` }], isError: true };
}
