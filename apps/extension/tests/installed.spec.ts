import type browser from "webextension-polyfill";
declare const chrome: typeof browser;
declare global {
  interface Window {
    sent: number;
  }
}
import { test, expect, chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
test("installed Chrome extension: actual pairing, scoped API, storage, insertion and disconnect", async () => {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "promptengine-installed-"),
  );
  const extension = path.join(root, "extension");
  fs.cpSync(path.resolve("dist/chrome"), extension, { recursive: true });
  // Browser automation cannot accept the native optional-host permission dialog or
  // click the native toolbar. Pregrant only fixture hosts in a TEMPORARY test copy.
  // Production manifests are never changed and still use user-granted activeTab.
  const manifest = JSON.parse(
    fs.readFileSync(path.join(extension, "manifest.json"), "utf8"),
  );
  manifest.host_permissions = ["http://localhost/*", "https://chatgpt.com/*"];
  fs.writeFileSync(
    path.join(extension, "manifest.json"),
    JSON.stringify(manifest),
  );
  const context = await chromium.launchPersistentContext(
    path.join(root, "profile"),
    {
      channel: "chromium",
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
        : {}),
      headless: true,
      args: [
        "--no-sandbox",
        "--no-zygote",
        `--disable-extensions-except=${extension}`,
        `--load-extension=${extension}`,
      ],
    },
  );
  try {
    let worker = context.serviceWorkers()[0];
    if (!worker) worker = await context.waitForEvent("serviceworker");
    const id = worker.url().split("/")[2];
    const popup = await context.newPage();
    await popup.goto(`chrome-extension://${id}/popup.html`);
    await popup.getByLabel("API server address").fill("http://localhost:5000");
    await popup.getByLabel("Web app address").fill("http://localhost:5173");
    await popup.getByRole("checkbox").check();
    await popup.getByRole("button", { name: "Connect workspace" }).click();
    await popup.getByRole("button", { name: "Create pairing code" }).click();
    const code = (await popup.locator(".pairing-code").innerText()).trim();
    expect(code).toMatch(/^\d{6}$/);
    const web = await context.newPage();
    await web.goto("http://localhost:5173/signup");
    await web
      .getByLabel("Email address")
      .fill(`extension-${Date.now()}@example.com`);
    await web.locator("#password").fill("extension-browser-test-password");
    await web.getByRole("button", { name: "Create account" }).click();
    await expect(web).toHaveURL("http://localhost:5173/workspace");
    await web.goto("http://localhost:5173/settings/extensions");
    await web.getByLabel("Pairing code").fill(code);
    await web.getByRole("button", { name: "Review browser" }).click();
    await web.getByRole("button", { name: "Approve this browser" }).click();
    await popup
      .getByRole("button", { name: "I approved this browser" })
      .click();
    await popup
      .getByLabel("What do you want to accomplish?")
      .fill("Build a client dashboard with PostgreSQL and role-based access.");
    await popup.getByRole("button", { name: "Build prompt" }).click();
    const prompt = await popup.getByLabel("Generated prompt").inputValue();
    expect(prompt).toContain("PostgreSQL");
    await expect(popup.getByText("Added", { exact: true })).toBeVisible();
    const saved = await worker.evaluate(async () => {
      const data = await chrome.storage.local.get("auth");
      return { auth: data.auth as { access_token: string; scopes: string[] } };
    });
    expect(saved.auth.access_token).toMatch(/^pe_ext_/);
    expect(saved.auth.scopes).toContain("refine");
    const chat = await context.newPage();
    await chat.route("https://chatgpt.com/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<!doctype html><form><textarea id="prompt-textarea">Existing draft</textarea><button type="submit">Send</button></form><script>window.sent=0;document.querySelector("form").addEventListener("submit",event=>{event.preventDefault();window.sent++})</script>',
      }),
    );
    await chat.goto("https://chatgpt.com/c/fixture");
    const tab = await worker.evaluate(async () => {
      const tabs = await chrome.tabs.query({});
      return tabs.find((t) => t.url === "https://chatgpt.com/c/fixture")?.id;
    });
    expect(tab).toBeDefined();
    await expect
      .poll(
        async () =>
          await worker.evaluate(async () =>
            Boolean(
              (
                (await chrome.storage.session.get("editor")).editor as
                  { result?: unknown } | undefined
              )?.result,
            ),
          ),
      )
      .toBe(true);
    await popup.close();
    const editor = await context.newPage();
    await editor.goto(`chrome-extension://${id}/popup.html?target=${tab}`);
    await expect(editor.getByLabel("Generated prompt")).toHaveValue(prompt);
    await editor.getByRole("button", { name: "Insert into ChatGPT" }).click();
    await expect(editor.getByRole("alertdialog")).toContainText("Replace");
    await expect(chat.locator("textarea")).toHaveValue("Existing draft");
    await editor
      .getByRole("button", { name: "Replace draft", exact: true })
      .click();
    await expect(chat.locator("textarea")).toHaveValue(prompt);
    expect(await chat.evaluate(() => window.sent)).toBe(0);
    const protectedStorage = await worker.evaluate(async (tabId) => {
      const result = await chrome.scripting.executeScript({
        target: { tabId },
        func: async () => {
          try {
            await chrome.storage.local.get("auth");
            return false;
          } catch {
            return true;
          }
        },
      });
      return result[0].result;
    }, tab!);
    expect(protectedStorage).toBe(true);
    await editor.getByRole("button", { name: "Workspace settings" }).click();
    await editor
      .getByRole("button", { name: "Disconnect this browser" })
      .click();
    await editor.getByRole("button", { name: "Confirm disconnect" }).click();
    await expect(
      editor.getByRole("heading", { name: "Pair this browser." }),
    ).toBeVisible();
    expect(
      (
        await worker.evaluate(
          async () => await chrome.storage.local.get("auth"),
        )
      ).auth,
    ).toBeUndefined();
    const denied = await web.request.get("http://localhost:5000/api/usage", {
      headers: { Authorization: `Bearer ${saved.auth.access_token}` },
    });
    expect(denied.status()).toBe(401);
    await expect(
      web.getByRole("button", { name: "Refresh devices" }),
    ).toBeVisible();
  } finally {
    await context.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
