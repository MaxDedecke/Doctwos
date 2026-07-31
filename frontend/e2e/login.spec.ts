import { expect, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL || "http://82.165.216.180:8000";
const USERNAME = process.env.E2E_USERNAME || "testuser";
const PASSWORD = process.env.E2E_PASSWORD || "";

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status !== testInfo.expectedStatus) {
    console.error("=== E2E TEST FAILED ===");
    console.error("Failed Test:", testInfo.title);
    console.error("Current Page URL:", page.url());
    try {
      console.error("Page HTML Content:\n", await page.content());
    } catch (e) {
      console.error("Failed to capture page content:", e);
    }
  }
});

test("local login lands on the authenticated app shell and the session works for API calls", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#username")).toBeVisible();

  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Anmelden|Sign in/ }).click();

  // Wait for the authenticated app shell and its project selector to load completely
  await expect(page.locator("#project-selector")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("#username")).not.toBeVisible();

  // The session cookie must work for actual API calls made from the browser context
  const projName = `e2e-project-${Date.now()}`;
  const createResp = await page.request.post(`${API_URL}/projects`, {
    data: { name: projName },
  });
  
  if (!createResp.ok()) {
    console.error("=== POST /projects FAILED ===");
    console.error("Status:", createResp.status());
    console.error("Body:", await createResp.text());
  }
  
  expect(createResp.ok()).toBeTruthy();
  const project = await createResp.json();

  // Projects render in the UI after reload
  await page.reload();
  await page.locator("#project-selector").click();
  await expect(page.getByText(projName)).toBeVisible();

  const deleteResp = await page.request.delete(`${API_URL}/projects/${project.id}`);
  if (!deleteResp.ok()) {
    console.error("=== DELETE /projects FAILED ===");
    console.error("Status:", deleteResp.status());
    console.error("Body:", await deleteResp.text());
  }
});
