import { expect, test } from "@playwright/test";

test("landing page and readiness", async ({ page, request }) => {
  const ready = await request.get("/api/health/ready");
  expect(ready.ok()).toBeTruthy();
  const body = await ready.json();
  expect(body.status).toBe("ok");

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator("body")).toContainText(/SAFe|DevOps|assessment/i);
});
