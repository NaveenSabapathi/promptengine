import { afterEach, describe, expect, it, vi } from "vitest";
import { api, APIException, post } from "./api";
import { safeCheckout } from "./utils";
afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_access_token=; max-age=0; path=/";
});
describe("cookie authenticated API boundary", () => {
  it("sends cookies and the separate CSRF token, without a bearer token", async () => {
    document.cookie = "csrf_access_token=test-csrf; path=/";
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetch);
    await post("/api/prompts", { title: "Example" });
    const options = fetch.mock.calls[0][1];
    expect(options.credentials).toBe("include");
    expect(options.headers.get("X-CSRF-TOKEN")).toBe("test-csrf");
    expect(options.headers.get("Authorization")).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("keeps the API error code and message for quota and billing failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "billing_uncertain",
              message: "Do not retry payment",
            },
          }),
          { status: 503 },
        ),
      ),
    );
    await expect(
      post("/api/billing/subscribe", { plan_tier: "pro" }),
    ).rejects.toMatchObject({
      code: "billing_uncertain",
      message: "Do not retry payment",
    });
  });
  it("allows empty delete responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    expect(await api("/api/prompts/id", { method: "DELETE" })).toBeUndefined();
  });
  it("clears an expired session on protected API calls", async () => {
    const expired = vi.fn();
    window.addEventListener("session-expired", expired);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "session_expired", message: "Sign in" },
          }),
          { status: 401 },
        ),
      ),
    );
    await expect(api("/api/usage")).rejects.toBeInstanceOf(APIException);
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener("session-expired", expired);
  });
  it("rejects calls outside the local API", async () => {
    await expect(api("https://example.com/api/usage")).rejects.toThrow(
      "local API",
    );
  });
});
describe("checkout destination validation", () => {
  it("allows only actual HTTPS Razorpay short links", () => {
    expect(safeCheckout("https://rzp.io/i/test")).toBe("https://rzp.io/i/test");
    for (const url of [
      "http://rzp.io/i/test",
      "https://rzp.io.attacker.com",
      "https://attacker@rzp.io",
      "javascript:alert(1)",
    ])
      expect(() => safeCheckout(url)).toThrow();
  });
});

it("rejects malformed successful API responses clearly", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("not JSON", { status: 200 })),
  );
  await expect(api("/api/usage")).rejects.toMatchObject({
    code: "invalid_response",
    status: 502,
  });
});

it("adds the active workspace only to asset and generation requests", async () => {
  sessionStorage.setItem("active-team", "team-id");
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
  await api("/api/prompts");
  expect(
    new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get("X-Team-ID"),
  ).toBe("team-id");
  await api("/api/billing/status");
  expect(
    new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get("X-Team-ID"),
  ).toBeNull();
  sessionStorage.clear();
});
