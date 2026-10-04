export class APIException extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export function csrfToken() {
  return document.cookie
    .split(";")
    .map((v) => v.trim())
    .find((v) => v.startsWith("csrf_access_token="))
    ?.slice("csrf_access_token=".length);
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/api/"))
    throw new Error("API requests must use a local API path");
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (
    options.method &&
    !["GET", "HEAD"].includes(options.method.toUpperCase())
  ) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-TOKEN", decodeURIComponent(csrf));
  }
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(path, {
      ...options,
      credentials: "include",
      headers,
      signal: controller.signal,
    });
    const data =
      response.status === 204
        ? undefined
        : await response.json().catch(() => undefined);
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith("/api/auth/"))
        window.dispatchEvent(new Event("session-expired"));
      throw new APIException(
        data?.error?.code || "request_failed",
        data?.error?.message ||
          `Request failed (${response.status}). Try again later.`,
        response.status,
      );
    }
    if (response.status !== 204 && data === undefined) {
      throw new APIException(
        "invalid_response",
        "The server returned an invalid response. Try again later.",
        502,
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof APIException) throw error;
    if (error instanceof DOMException && error.name === "AbortError")
      throw new Error(
        "The request timed out. Refresh the status before retrying a payment.",
      );
    throw new Error(
      "Unable to reach the server. Check your connection and try again.",
    );
  } finally {
    clearTimeout(timer);
  }
}
export const post = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again.";
}
