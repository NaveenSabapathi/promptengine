import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Settings from "./Settings";
import { api, post } from "@/lib/api";
vi.mock("@/auth", () => ({
  useAuth: () => ({
    user: { email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" },
    linked: [],
  }),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: vi.fn(),
  post: vi.fn(),
}));
let status: {
  plan_tier: string;
  daily_ai_limit: number;
  billing_enabled: boolean;
  subscription: unknown;
};
beforeEach(() => {
  vi.mocked(post).mockReset();
  status = {
    plan_tier: "free",
    daily_ai_limit: 10,
    billing_enabled: true,
    subscription: null,
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/billing/status") return status as never;
    if (path === "/api/billing/plans")
      return {
        billing_enabled: true,
        plans: [{ tier: "pro", amount_paise: 49900, daily_ai_limit: 100 }],
      } as never;
    if (path === "/api/usage")
      return { used: 0, daily_ai_limit: 10, remaining: 10 } as never;
    if (path === "/api/generation-metrics?days=30")
      return { groups: [] } as never;
    return { providers: { google: false, microsoft: false } } as never;
  });
});
describe("payment status is a server decision", () => {
  it("never retries an uncertain checkout or grants Pro based on the client request", async () => {
    const user = userEvent.setup();
    vi.mocked(post).mockRejectedValue(
      new Error("Checkout needs reconciliation; do not retry payment"),
    );
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: "Upgrade to Pro" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "do not retry payment",
    );
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Free", { exact: true })).toBeInTheDocument();
  });
  it("disables a new purchase for an uncertain existing subscription", async () => {
    status.subscription = {
      id: "attempt",
      status: "uncertain",
      amount_paise: 49900,
      currency: "INR",
      current_end: null,
      cancel_at_cycle_end: false,
    };
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", {
        name: "Subscription needs attention",
      }),
    ).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });
  it("requires explicit confirmation before a period-end cancellation", async () => {
    const user = userEvent.setup();
    status = {
      ...status,
      plan_tier: "pro",
      subscription: {
        id: "attempt",
        razorpay_subscription_id: "sub_existing",
        status: "active",
        amount_paise: 49900,
        currency: "INR",
        current_end: "2026-11-01T00:00:00Z",
        cancel_at_cycle_end: false,
      },
    };
    vi.mocked(post).mockResolvedValue({} as never);
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Cancel subscription",
      }),
    );
    expect(post).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Confirm cancellation" }),
    );
    expect(post).toHaveBeenCalledWith("/api/billing/cancel", {
      at_cycle_end: true,
    });
  });
});
