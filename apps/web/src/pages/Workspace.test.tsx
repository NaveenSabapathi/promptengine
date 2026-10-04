import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Workspace from "./Workspace";
import { api, post } from "@/lib/api";
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: vi.fn(),
  post: vi.fn(),
}));
const preset = {
  id: "coding",
  name: "Coding",
  role: "Act as a senior engineer",
  required_fields: { objective: "Task", language: "Language?" },
  optional_fields: {},
  output_constraints: [],
};
beforeEach(() => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/presets")
      return {
        presets: [preset],
        tones: ["professional"],
        modes: ["Build", "Compact"],
      } as never;
    if (path === "/api/auth/capabilities")
      return { providers: {}, ai_enabled: true } as never;
    if (path === "/api/custom-presets") return { presets: [] } as never;
    return { remaining: 10, daily_ai_limit: 10, used: 0 } as never;
  });
});
describe("workspace decisions", () => {
  it("uses local compiling by default, shows added tokens, and saves only on request", async () => {
    const user = userEvent.setup();
    vi.mocked(post).mockClear();
    vi.mocked(post).mockResolvedValue({
      prompt: "Act as a senior engineer. Build a dashboard.",
      engine: "local",
      metrics: {
        raw_tokens: 4,
        generated_tokens: 12,
        token_difference: -8,
        reduction_percent: -200,
        is_reduction: false,
      },
      clarification_questions: ["Which language?"],
      assumptions: [],
    } as never);
    render(
      <MemoryRouter>
        <Workspace />
      </MemoryRouter>,
    );
    await user.type(
      await screen.findByLabelText("What do you want to accomplish?"),
      "Build a dashboard",
    );
    await user.click(screen.getByRole("button", { name: "Build prompt" }));
    expect(post).toHaveBeenCalledWith(
      "/api/compile",
      expect.objectContaining({
        raw_input: "Build a dashboard",
        preset: "coding",
      }),
    );
    expect(await screen.findByText("Tokens added")).toBeInTheDocument();
    expect(screen.getByText("Worth clarifying")).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Save to library" }));
    await user.click(screen.getByRole("button", { name: "Save prompt" }));
    expect(post).toHaveBeenLastCalledWith(
      "/api/prompts",
      expect.objectContaining({
        content: "Act as a senior engineer. Build a dashboard.",
      }),
    );
  });
  it("surfaces provider failures and never presents them as a generated prompt", async () => {
    const user = userEvent.setup();
    vi.mocked(post).mockRejectedValue(
      new Error("AI provider timed out. Try again later."),
    );
    render(
      <MemoryRouter>
        <Workspace />
      </MemoryRouter>,
    );
    await user.type(
      await screen.findByLabelText("What do you want to accomplish?"),
      "Build a dashboard",
    );
    await user.selectOptions(screen.getByLabelText("Generation method"), "ai");
    await user.click(screen.getByRole("button", { name: "Refine with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "AI provider timed out",
    );
    expect(screen.queryByLabelText("Generated prompt")).not.toBeInTheDocument();
  });
});
