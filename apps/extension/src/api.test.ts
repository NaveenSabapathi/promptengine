import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { request } from "./api";
const mocks = vi.hoisted(() => ({
  contains: vi.fn(),
  read: vi.fn(),
  clear: vi.fn(),
}));
vi.mock("./platform", () => ({
  default: { permissions: { contains: mocks.contains } },
}));
vi.mock("./storage", () => ({
  readStored: mocks.read,
  clearAuth: mocks.clear,
  hostPermission: () => "https://workspace.example.com/*",
}));
beforeEach(() => {
  mocks.contains.mockResolvedValue(true);
  mocks.clear.mockReset();
  mocks.read.mockResolvedValue({
    settings: { apiOrigin: "https://workspace.example.com", consent: true },
    auth: {
      access_token: "pe_ext_scoped",
      token_id: "one",
      expires_at: "2099-01-01T00:00:00Z",
    },
  });
});
afterEach(() => vi.unstubAllGlobals());
it("sends only the scoped bearer token, omits web cookies, and rejects redirects", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ prompt: "Example" })));
  vi.stubGlobal("fetch", fetch);
  await request("/api/compile", { raw_input: "Task" });
  const [url, options] = fetch.mock.calls[0];
  expect(url).toBe("https://workspace.example.com/api/compile");
  expect(options.headers.Authorization).toBe("Bearer pe_ext_scoped");
  expect(options.credentials).toBe("omit");
  expect(options.redirect).toBe("error");
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("does not transmit an existing token when creating or exchanging a pairing code", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: "123456" })));
  vi.stubGlobal("fetch", fetch);
  await request("/api/extension/pairing", { device_name: "Browser" });
  expect(fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
});
it("clears the matching revoked token and returns the original authorization error", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unauthorized", message: "Revoked" },
          }),
          { status: 401 },
        ),
      ),
  );
  await expect(request("/api/usage")).rejects.toMatchObject({
    code: "unauthorized",
  });
  expect(mocks.clear).toHaveBeenCalledOnce();
});
it("does not clear a newly paired token when an older request fails", async () => {
  mocks.read
    .mockResolvedValueOnce({
      settings: { apiOrigin: "https://workspace.example.com", consent: true },
      auth: {
        token_id: "old",
        access_token: "pe_ext_old",
        expires_at: "2099-01-01T00:00:00Z",
      },
    })
    .mockResolvedValueOnce({ auth: { token_id: "new" } });
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unauthorized", message: "Revoked" },
          }),
          { status: 401 },
        ),
      ),
  );
  await expect(request("/api/usage")).rejects.toThrow("Revoked");
  expect(mocks.clear).not.toHaveBeenCalled();
});
it("blocks calls without host permission or outside the extension API allowlist", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  mocks.contains.mockResolvedValue(false);
  await expect(request("/api/usage")).rejects.toMatchObject({
    code: "permission_required",
  });
  await expect(request("/api/billing/subscribe")).rejects.toThrow(
    "Unsupported",
  );
  expect(fetch).not.toHaveBeenCalled();
});
