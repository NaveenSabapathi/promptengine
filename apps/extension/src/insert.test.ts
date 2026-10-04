import { beforeEach, expect, it, vi } from "vitest";
import { insertIntoTab, copyPrompt } from "./insert";
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  manifest: vi.fn(),
  scripting: vi.fn(),
  legacy: vi.fn(),
}));
vi.mock("./platform", () => ({
  default: {
    tabs: { get: mocks.get, executeScript: mocks.legacy },
    runtime: { getManifest: mocks.manifest },
    scripting: { executeScript: mocks.scripting },
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockResolvedValue({ url: "https://chatgpt.com/c/1" });
  mocks.manifest.mockReturnValue({ manifest_version: 3 });
});
it("passes only prompt text and the explicit replace flag into the active tab", async () => {
  mocks.scripting.mockResolvedValue([
    { result: { status: "inserted", site: "ChatGPT" } },
  ]);
  expect((await insertIntoTab(7, "Prompt")).status).toBe("inserted");
  expect(mocks.scripting).toHaveBeenCalledWith(
    expect.objectContaining({ target: { tabId: 7 }, args: ["Prompt", false] }),
  );
  expect(JSON.stringify(mocks.scripting.mock.calls[0][0])).not.toContain(
    "token",
  );
});
it("falls back on unsupported and denied tabs without injecting", async () => {
  mocks.get.mockResolvedValue({ url: "https://example.com" });
  expect((await insertIntoTab(7, "Prompt")).status).toBe("unsupported");
  expect(mocks.scripting).not.toHaveBeenCalled();
  mocks.get.mockRejectedValue(new Error("Denied"));
  expect((await insertIntoTab(7, "Prompt")).status).toBe("blocked");
});
it("serializes MV2 arguments rather than interpolating prompt text as code", async () => {
  mocks.manifest.mockReturnValue({ manifest_version: 2 });
  mocks.legacy.mockResolvedValue([{ status: "inserted" }]);
  const text = 'quote "); window.evil = true; //\n\u2028';
  await insertIntoTab(7, text);
  const code = mocks.legacy.mock.calls[0][1].code;
  expect(code).toContain(JSON.stringify(text).replace(/\u2028/g, "\\u2028"));
  expect(code.endsWith(",false);")).toBe(true);
});
it("falls back from the clipboard API to selected plain text and reports denial", async () => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error("Denied")) },
  });
  const command = vi.fn(() => true);
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: command,
  });
  await copyPrompt("Text");
  expect(command).toHaveBeenCalledWith("copy");
  expect(document.querySelector("textarea")).toBeNull();
  command.mockReturnValue(false);
  await expect(copyPrompt("Text")).rejects.toThrow("copy it manually");
});
