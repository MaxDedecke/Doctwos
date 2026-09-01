import { describe, expect, it } from "vitest";
import { cn } from "./utils";
import { normalizeInitialUserMessage } from "./chatMessage";
import { resolvePanelNavigationTarget } from "./panelNavigation";

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

describe("normalizeInitialUserMessage", () => {
  it("removes the accidental zero from the first greeting question", () => {
    expect(normalizeInitialUserMessage("0 Wer bist du ?", true)).toBe("Wer bist du ?");
  });

  it("does not alter later or intentionally numbered messages", () => {
    expect(normalizeInitialUserMessage("0 Wer bist du ?", false)).toBe("0 Wer bist du ?");
    expect(normalizeInitialUserMessage("0 Welche Programme ruft dieser Job auf?", true)).toBe("0 Welche Programme ruft dieser Job auf?");
  });
});

describe("resolvePanelNavigationTarget", () => {
  it("uses a live matching panel before a frozen one", () => {
    expect(resolvePanelNavigationTarget({
      targetType: "code",
      panelConfigs: ["code", "code"],
      panelFrozen: [true, false],
    })).toEqual({ targetIndex: 1, shouldOpenNewPanel: false, ignored: false });
  });

  it("does not target a frozen code panel from the Call Graph", () => {
    expect(resolvePanelNavigationTarget({
      targetType: "code",
      panelConfigs: ["callgraph", "code"],
      panelFrozen: [true, true],
      preserveFrozenTarget: true,
    })).toEqual({ targetIndex: null, shouldOpenNewPanel: true, ignored: false });

    expect(resolvePanelNavigationTarget({
      targetType: "code",
      panelConfigs: ["callgraph", "code", "doc", "chat"],
      panelFrozen: [true, true, false, false],
      preserveFrozenTarget: true,
    })).toEqual({ targetIndex: null, shouldOpenNewPanel: false, ignored: true });
  });
});
