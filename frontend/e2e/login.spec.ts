import { expect, test } from "@playwright/test";

const API_URL = process.env.E2E_API_URL || "http://82.165.216.180:8000";

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

test("OIDC login redirect lands on the authenticated app shell and the session works for API calls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Mit SSO anmelden")).toBeVisible();

  await page.getByText("Mit SSO anmelden").click();

  // Keycloak login form
  await page.waitForURL(/realms\/doctus\/protocol\/openid-connect\/auth/);
  await page.locator("#username").fill("testuser");
  await page.locator("#password").fill("testpass");
  await page.locator("#kc-login").click();

  // Back on the frontend, authenticated app shell instead of the login screen
  await page.waitForURL((url) => 
    !url.toString().includes("doctus-test-keycloak") &&
    !url.toString().includes("protocol/openid-connect") &&
    !url.toString().includes("realms/doctus")
  );
  await expect(page.getByText("Mit SSO anmelden")).not.toBeVisible();

  // Wait for the authenticated app shell and its project selector to load completely
  await expect(page.locator("#project-selector")).toBeVisible({ timeout: 10_000 });

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
