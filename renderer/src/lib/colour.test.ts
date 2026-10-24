import { describe, expect, it } from "vitest";
import { readableOn } from "./colour";

describe("readableOn", () => {
  it("puts white on dark brand colours and near-black on light ones", () => {
    expect(readableOn("#111111")).toBe("#FFFFFF");
    expect(readableOn("#1E3A8A")).toBe("#FFFFFF");
    expect(readableOn("#FFD400")).toBe("#111111");
    expect(readableOn("#FFFFFF")).toBe("#111111");
  });

  it("refuses a colour the config should have rejected, instead of guessing white", () => {
    expect(() => readableOn("red")).toThrow(/#RRGGBB/);
    expect(() => readableOn("#FFF")).toThrow(/#RRGGBB/);
  });
});
