import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import Security from "./Security";
const { api, post } = vi.hoisted(() => ({ api: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, post, errorText: (e: Error) => e.message }));
vi.mock("@/auth", () => ({
  useAuth: () => ({ user: { is_admin: false }, refresh: vi.fn() }),
}));
describe("security privacy controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("makes collection explicit and revocation deletes records", async () => {
    api.mockResolvedValue({
      enabled: false,
      recovery_codes_remaining: 0,
      dataset_consent: false,
    });
    post.mockResolvedValue({ enabled: true });
    render(<Security />);
    await screen.findByRole("button", { name: "Opt in to training data" });
    expect(screen.getByText(/Off by default/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Opt in to training data" }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/dataset/consent", {
        enabled: true,
      }),
    );
  });
  it("does not hide a failed MFA verification", async () => {
    api.mockResolvedValue({
      enabled: true,
      recovery_codes_remaining: 8,
      dataset_consent: false,
    });
    post.mockRejectedValue(new Error("Code already used"));
    render(<Security />);
    await screen.findByLabelText("Authenticator or recovery code");
    fireEvent.change(screen.getByLabelText("Authenticator or recovery code"), {
      target: { value: "123456" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Verify sensitive actions" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Code already used",
    );
  });
});
