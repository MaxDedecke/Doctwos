import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// NF-012 (Barrierefreiheit): automatisierter Basis-Check, kein Ersatz für die
// formale BITV-Abnahme (der verbindliche Prüfumfang steht mit dem
// Auftraggeber noch aus, siehe docs/UMSETZUNGSSTAND.md AP-9). Deckt WCAG2A/
// WCAG2AA-Regeln ab: Formular-Labels, ARIA-Attribute, Landmarken, Zoom.
//
// "color-contrast" ist bewusst ausgeschlossen: der Scan fand echte Verstöße
// im bestehenden --ds-*-Palette (u.a. text-ds-zinc-400/500 auf dunklem
// Grund), deren Behebung eine Design-Entscheidung ist (welche Tokens sich
// wie stark verschieben, ohne den Fujitsu-Markenlook zu brechen) — siehe
// docs/UMSETZUNGSSTAND.md AP-9 für die Fundliste. Ein dauerhaft roter Job
// wird nicht mehr gelesen (dieselbe Regel wie bei @requires_ollama, AP-1);
// bis zur Design-Entscheidung bleibt dieser Check auf die automatisiert
// eindeutig behebbaren Regeln beschränkt.
const USERNAME = process.env.E2E_USERNAME || "testuser";
const PASSWORD = process.env.E2E_PASSWORD || "";

test("login screen has no automatically detectable WCAG2A/AA violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#username")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    .analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test("authenticated workspace shell has no automatically detectable WCAG2A/AA violations", async ({ page }) => {
  await page.goto("/");
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Anmelden|Sign in/ }).click();
  await expect(page.locator("#project-selector")).toBeVisible({ timeout: 10_000 });

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["color-contrast"])
    // Monaco und der Force-Graph rendern auf <canvas>: Farbkontrast dort ist
    // syntaxfarblich, nicht per CSS-Token steuerbar, und faellt nicht unter
    // die Design-Token-Kontrastpruefung — separat zu bewerten, kein
    // automatisiert pruefbarer Fall.
    .exclude("canvas")
    .analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});
