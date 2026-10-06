import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Login from "./Login";
import { APIException } from "@/lib/api";
const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  api: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/auth", () => ({
  useAuth: () => ({ user: null, refresh: mocks.refresh }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  post: mocks.post,
  api: mocks.api,
}));
function Destination() {
  const location = useLocation();
  return (
    <output aria-label="Destination">
      {location.pathname + location.hash}
    </output>
  );
}
function setup(from = "/workspace") {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Destination />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "member@example.com" },
  });
  fireEvent.change(screen.getByLabelText(/Password/), {
    target: { value: "correct-long-password" },
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.api.mockResolvedValue({
    providers: { google: false, microsoft: false },
    ai_enabled: false,
  });
  mocks.refresh.mockResolvedValue(undefined);
  mocks.post.mockResolvedValue({ user: { id: "member" } });
});
describe("login verification and invitation destination", () => {
  it("preserves the private invitation fragment after password login", async () => {
    setup("/teams#invite=abcdefghijklmnopqrstuvwxyz123456");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByLabelText("Destination")).toHaveTextContent(
      "/teams#invite=abcdefghijklmnopqrstuvwxyz123456",
    );
  });
  it("requests MFA without navigating or accepting an incomplete login", async () => {
    mocks.post.mockRejectedValueOnce(
      new APIException("mfa_required", "Enter authenticator", 403),
    );
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const code = await screen.findByLabelText("Authenticator or recovery code");
    expect(mocks.refresh).not.toHaveBeenCalled();
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenLastCalledWith(
        "/api/auth/login",
        expect.objectContaining({ code: "123456" }),
      ),
    );
    expect(await screen.findByLabelText("Destination")).toHaveTextContent(
      "/workspace",
    );
  });
});
