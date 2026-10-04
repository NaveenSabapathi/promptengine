import { describe, expect, it, vi } from "vitest";
vi.mock("./platform", () => ({ default: {}, protectStorage: vi.fn() }));
import { normalizeOrigin, hostPermission, approvalURL } from "./storage";
describe("workspace boundaries", () => {
  it("permits HTTPS and explicit loopback development only", () => {
    expect(normalizeOrigin("https://workspace.example.com/")).toBe(
      "https://workspace.example.com",
    );
    expect(normalizeOrigin("http://localhost:5000")).toBe(
      "http://localhost:5000",
    );
    for (const url of [
      "http://workspace.example.com",
      "https://user:secret@example.com",
      "https://example.com/path",
      "https://example.com/?token=secret",
      "https://example.com/#token",
      "http://localhost.evil.com",
      "file:///tmp/app",
      "http://192.168.1.2",
    ])
      expect(() => normalizeOrigin(url)).toThrow();
  });
  it("requests only the chosen host and validates approval against the configured web origin", () => {
    expect(hostPermission("http://localhost:5000")).toBe("http://localhost/*");
    const config = {
      apiOrigin: "http://localhost:5000",
      webOrigin: "http://localhost:5173",
      deviceName: "Browser",
      consent: true as const,
    };
    expect(
      approvalURL("http://localhost:5173/settings/extensions", config),
    ).toBe("http://localhost:5173/settings/extensions");
    for (const url of [
      "https://attacker.com/settings/extensions",
      "http://localhost:5173/settings/extensions?code=123456",
      "http://localhost:5173/login",
    ])
      expect(() => approvalURL(url, config)).toThrow();
  });
});
