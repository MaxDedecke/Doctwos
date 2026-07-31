import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins plain class strings", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy values", () => {
    expect(cn("a", false, undefined, null, "b")).toBe("a b");
  });

  it("lets the later Tailwind class win on conflicting utilities", () => {
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("merges conditional classes from an object", () => {
    expect(cn("base", { active: true, hidden: false })).toBe("base active");
  });
});
