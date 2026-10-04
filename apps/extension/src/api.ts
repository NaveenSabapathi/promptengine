import browser from "./platform";
import { readStored, clearAuth, hostPermission } from "./storage";
export class ExtensionError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}
const publicPaths = new Set([
  "/api/presets",
  "/api/auth/capabilities",
  "/api/extension/pairing",
  "/api/extension/pairing/exchange",
]);
const allowedPaths = new Set([
  ...publicPaths,
  "/api/compile",
  "/api/refine",
  "/api/usage",
  "/api/custom-presets",
  "/api/prompts",
  "/api/extension/disconnect",
]);
export async function request<T>(path: string, data?: unknown): Promise<T> {
  if (!allowedPaths.has(path))
    throw new Error("Unsupported extension API path");
  const { settings, auth } = await readStored();
  if (!settings?.consent) throw new Error("Connect your workspace first.");
  if (
    !(await browser.permissions.contains({
      origins: [hostPermission(settings.apiOrigin)],
    }))
  )
    throw new ExtensionError(
      "permission_required",
      "Allow access to your workspace server in Settings.",
    );
  const headers: Record<string, string> = { Accept: "application/json" };
  if (data !== undefined) headers["Content-Type"] = "application/json";
  if (!publicPaths.has(path)) {
    if (!auth || new Date(auth.expires_at).getTime() <= Date.now()) {
      await clearAuth();
      window.dispatchEvent(new Event("extension-expired"));
      throw new ExtensionError("unauthorized", "Pair this browser again.");
    }
    headers.Authorization = `Bearer ${auth.access_token}`;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(settings.apiOrigin + path, {
      method: data === undefined ? "GET" : "POST",
      headers,
      body: data === undefined ? undefined : JSON.stringify(data),
      credentials: "omit",
      redirect: "error",
      signal: controller.signal,
    });
    const body = await response.json().catch(() => undefined);
    if (!response.ok) {
      if (response.status === 401 && !publicPaths.has(path)) {
        const current = await readStored();
        if (current.auth?.token_id === auth?.token_id) {
          await clearAuth();
          window.dispatchEvent(new Event("extension-expired"));
        }
      }
      throw new ExtensionError(
        body?.error?.code || "request_failed",
        body?.error?.message || `Request failed (${response.status}).`,
        response.status,
      );
    }
    if (!body)
      throw new ExtensionError(
        "invalid_response",
        "The server returned an invalid response.",
      );
    return body as T;
  } catch (error) {
    if (error instanceof ExtensionError) throw error;
    if (error instanceof DOMException && error.name === "AbortError")
      throw new Error("The request timed out. Try again later.");
    throw new Error(
      "Cannot reach your workspace. Check its address and your connection.",
    );
  } finally {
    clearTimeout(timer);
  }
}
export function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again.";
}
