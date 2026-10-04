import { test, expect } from "@playwright/test";
import fs from "node:fs";
import AxeBuilder from "@axe-core/playwright";
const output = process.env.WEB_SCREENSHOT_DIR;
async function shot(page: import("@playwright/test").Page, name: string) {
  if (output) {
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: `${output}/${name}.png`, fullPage: true });
  }
}
test("real API: signup, compile, save, search, edit, custom preset, billing, revoke, logout", async ({
  page,
}) => {
  const email = `browser-${Date.now()}@example.com`;
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Your rough idea. A sharper starting point.",
    }),
  ).toBeVisible();
  await expect(page.getByText("PLANNED PRICING")).toBeVisible();
  await shot(page, "landing-desktop");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("link", { name: "Get started" }).click();
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toBeDisabled();
  await page.getByLabel("Email address").fill(email);
  await page.locator("#password").fill("browser-test-password-2026");
  await shot(page, "signup-desktop");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/workspace");
  await expect(page.getByLabel("Choose your preset")).toBeVisible();
  await shot(page, "workspace-desktop");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "access_token_cookie")?.httpOnly).toBe(
    true,
  );
  expect(cookies.find((c) => c.name === "csrf_access_token")?.httpOnly).toBe(
    false,
  );
  await page
    .getByLabel("What do you want to accomplish?")
    .fill(
      "Build a PostgreSQL-backed customer dashboard with search and role-based access.",
    );
  await page.getByRole("button", { name: "Add context & constraints" }).click();
  await page.getByLabel("stack Core context").fill("Python and Flask");
  await page
    .getByLabel("deliverable Core context")
    .fill("Complete source files and tests");
  await page.getByRole("button", { name: "Build prompt" }).click();
  await expect(page.getByLabel("Generated prompt")).toHaveValue(/PostgreSQL/);
  await expect(page.getByText("Tokens added")).toBeVisible();
  await shot(page, "workspace-generated");
  await page.getByRole("button", { name: "Save to library" }).click();
  await page.getByLabel("Prompt title").fill("Client dashboard");
  await page.getByLabel("Tags").fill("client, dashboard");
  await page.getByRole("button", { name: "Save prompt", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Prompt saved to your library.",
  );
  await page.getByRole("link", { name: "Saved prompts", exact: true }).click();
  await page.getByLabel("Search saved prompt titles").fill("Client");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Client dashboard", exact: true }),
  ).toBeVisible();
  await shot(page, "history-desktop");
  await page.getByRole("button", { name: "Edit Client dashboard" }).click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Updated client dashboard");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("button", { name: "Updated client dashboard", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Custom presets", exact: true }).click();
  await page.getByRole("button", { name: "New preset" }).click();
  await page.getByLabel("Preset name").fill("Client brief");
  await page
    .getByLabel("Assistant role")
    .fill("Act as a corporate project manager.");
  await page.getByRole("button", { name: "Save preset" }).click();
  await expect(
    page.getByRole("heading", { name: "Client brief" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Prompt editor", exact: true }).click();
  await expect(
    page
      .getByLabel("Choose your preset")
      .locator("option", { hasText: "Client brief" }),
  ).toHaveCount(1);
  await page
    .getByLabel("Choose your preset")
    .selectOption({ label: "Client brief" });
  await page
    .getByLabel("What do you want to accomplish?")
    .fill("Define a two-week customer portal project.");
  await page.getByRole("button", { name: "Build prompt" }).click();
  await expect(page.getByLabel("Generated prompt")).toHaveValue(
    /corporate project manager/,
  );
  await page
    .getByRole("link", { name: "Settings & billing", exact: true })
    .click();
  await expect(
    page.getByText("Free beta · paid checkout disabled"),
  ).toBeVisible();
  await expect(page.getByText("0 / 10", { exact: false })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Upgrade to Pro" }),
  ).toHaveCount(0);
  await shot(page, "settings-desktop");
  await page.getByRole("link", { name: "Manage connected browsers" }).click();
  const created = await page.request.post("/api/extension/pairing", {
    data: { device_name: "E2E browser" },
  });
  expect(created.status()).toBe(201);
  const pairing = await created.json();
  await page.getByLabel("Pairing code").fill(pairing.code);
  await page.getByRole("button", { name: "Review browser" }).click();
  await expect(
    page.getByRole("heading", { name: "E2E browser" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve this browser" }).click();
  const exchanged = await page.request.post("/api/extension/pairing/exchange", {
    data: {
      pairing_id: pairing.pairing_id,
      code: pairing.code,
      device_secret: pairing.device_secret,
    },
  });
  expect(exchanged.status()).toBe(200);
  const token = await exchanged.json();
  await page.getByRole("button", { name: "Refresh devices" }).click();
  await expect(page.getByText("E2E browser", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  await page
    .getByRole("button", { name: "Revoke browser", exact: true })
    .click();
  const denied = await page.request.get("/api/usage", {
    headers: { Authorization: `Bearer ${token.access_token}` },
  });
  expect(denied.status()).toBe(401);
  await page.goto("/workspace");
  await page.setViewportSize({ width: 390, height: 844 });
  await shot(page, "workspace-mobile");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL("/login");
  await page.goto("/history");
  await expect(page).toHaveURL("/login");
  await page.getByLabel("Email address").fill(email);
  await page.locator("#password").fill("browser-test-password-2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/history");
  await page
    .getByRole("button", { name: "Delete Updated client dashboard" })
    .click();
  await page
    .getByRole("button", { name: "Delete prompt", exact: true })
    .click();
  await expect(page.getByText("Your library starts here")).toBeVisible();
});
test("direct routes, unknown page, and provider callback failure", async ({
  page,
}) => {
  await page.goto("/login?error=account_link_required");
  await expect(page.getByRole("alert")).toContainText("link the provider");
  await page.goto("/api/auth/microsoft/callback");
  await expect(page).toHaveURL(/\/login\?error=provider_not_configured/);
  await expect(page.getByRole("alert")).toContainText("not available");
  await page.goto("/not-a-page");
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();
});
