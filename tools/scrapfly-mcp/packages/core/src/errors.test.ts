import { describe, it, expect } from "vitest";
import { describeError } from "./errors.js";

describe("describeError", () => {
  it("extracts message and code from an Error with scrapfly fields", () => {
    const err = Object.assign(new Error("upstream blocked"), {
      code: "ERR::ASP::SHIELD_PROTECTION_FAILED",
      retryable: true,
    });
    expect(describeError(err)).toEqual({
      message: "upstream blocked",
      retryable: true,
      code: "ERR::ASP::SHIELD_PROTECTION_FAILED",
    });
  });

  it("defaults retryable to false for a plain Error", () => {
    expect(describeError(new Error("boom"))).toEqual({ message: "boom", retryable: false });
  });

  it("stringifies non-Error throwables", () => {
    expect(describeError("nope")).toEqual({ message: "nope", retryable: false });
  });
});
