import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
const mocks = vi.hoisted(() => ({
  read: vi.fn(),
  write: vi.fn(),
  editor: vi.fn(),
  saveEditor: vi.fn(),
  clear: vi.fn(),
  request: vi.fn(),
  insert: vi.fn(),
  copy: vi.fn(),
  create: vi.fn(),
  remove: vi.fn(),
  permission: vi.fn(),
}));
vi.mock("./platform", () => ({
  default: {
    tabs: {
      query: async () => [{ id: 7 }],
      get: async () => ({ url: "https://chatgpt.com/c/1" }),
      create: mocks.create,
    },
    storage: { local: { remove: mocks.remove } },
    runtime: { getURL: (path: string) => "chrome-extension://example/" + path },
    permissions: { request: mocks.permission, remove: async () => true },
  },
}));
vi.mock("./storage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./storage")>()),
  readStored: mocks.read,
  setStored: mocks.write,
  editorState: mocks.editor,
  saveEditor: mocks.saveEditor,
  clearAuth: mocks.clear,
}));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  request: mocks.request,
}));
vi.mock("./insert", () => ({
  insertIntoTab: mocks.insert,
  copyPrompt: mocks.copy,
}));
const settings = {
  apiOrigin: "https://workspace.example.com",
  webOrigin: "https://workspace.example.com",
  deviceName: "My browser",
  consent: true,
};
const auth = {
  access_token: "pe_ext_test_only",
  token_id: "token-id",
  token_type: "Bearer",
  expires_at: "2099-01-01T00:00:00Z",
  scopes: ["refine"],
};
const output = {
  prompt: "A crafted plain text prompt.",
  engine: "local",
  metrics: {
    raw_tokens: 4,
    generated_tokens: 8,
    token_difference: -4,
    is_reduction: false,
  },
  clarification_questions: [],
  assumptions: [],
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.read.mockResolvedValue({ settings });
  mocks.editor.mockResolvedValue(undefined);
  mocks.saveEditor.mockResolvedValue(undefined);
  mocks.write.mockResolvedValue(undefined);
  mocks.permission.mockResolvedValue(true);
  mocks.request.mockImplementation(async (path: string) => {
    if (path === "/api/presets")
      return {
        presets: [
          {
            id: "coding",
            name: "Coding",
            role: "Engineer",
            required_fields: { objective: "Task" },
            optional_fields: {},
            output_constraints: [],
          },
        ],
        tones: ["professional"],
        modes: ["Build", "Compact"],
      };
    if (path === "/api/usage")
      return { remaining: 10, daily_ai_limit: 10, used: 0 };
    if (path === "/api/auth/capabilities") return { ai_enabled: false };
    if (path === "/api/custom-presets") return { presets: [] };
    if (path === "/api/compile") return output;
    if (path === "/api/extension/pairing")
      return {
        pairing_id: "pair-id",
        code: "123456",
        device_secret: "device-secret",
        expires_at: "2099-01-01T00:00:00Z",
        approval_url: settings.webOrigin + "/settings/extensions",
        scopes: ["refine"],
      };
    if (path === "/api/extension/pairing/exchange") return auth;
    return {};
  });
});
describe("popup workflow", () => {
  it("persists pairing before opening approval and stores the scoped token only after exchange", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Create pairing code" }),
    );
    expect(await screen.findByText("123456")).toBeInTheDocument();
    expect(mocks.write).toHaveBeenCalledWith(
      expect.objectContaining({
        pairing: expect.objectContaining({ device_secret: "device-secret" }),
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "Open approval page" }),
    );
    expect(mocks.create).toHaveBeenCalledWith({
      url: "https://workspace.example.com/settings/extensions",
    });
    expect(JSON.stringify(mocks.create.mock.calls)).not.toContain(
      "device-secret",
    );
    await user.click(
      screen.getByRole("button", { name: "I approved this browser" }),
    );
    expect(
      await screen.findByLabelText("What do you want to accomplish?"),
    ).toBeInTheDocument();
    expect(mocks.write).toHaveBeenCalledWith({ auth });
  });
  it("requires a second explicit action to replace an existing chat draft", async () => {
    mocks.read.mockResolvedValue({ settings, auth });
    const user = userEvent.setup();
    mocks.insert
      .mockResolvedValueOnce({
        status: "occupied",
        message: "There is a draft.",
      })
      .mockResolvedValueOnce({
        status: "inserted",
        message: "Inserted without sending.",
      });
    render(<App />);
    await user.type(
      await screen.findByLabelText("What do you want to accomplish?"),
      "Build a dashboard",
    );
    await user.click(screen.getByRole("button", { name: "Build prompt" }));
    expect(await screen.findByLabelText("Generated prompt")).toHaveValue(
      output.prompt,
    );
    expect(screen.getByText("Added", { exact: true })).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Insert into ChatGPT" }),
    );
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Replace the existing chat draft",
    );
    expect(mocks.insert).toHaveBeenCalledTimes(1);
    expect(mocks.insert).toHaveBeenCalledWith(7, output.prompt, false);
    await user.click(screen.getByRole("button", { name: "Replace draft" }));
    expect(mocks.insert).toHaveBeenLastCalledWith(7, output.prompt, true);
    expect(mocks.copy).not.toHaveBeenCalled();
  });
  it("copies the prompt when tab insertion is denied", async () => {
    mocks.read.mockResolvedValue({ settings, auth });
    mocks.insert.mockResolvedValue({
      status: "blocked",
      message: "Tab access was denied.",
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(
      await screen.findByLabelText("What do you want to accomplish?"),
      "A task",
    );
    await user.click(screen.getByRole("button", { name: "Build prompt" }));
    await screen.findByLabelText("Generated prompt");
    await user.click(
      screen.getByRole("button", { name: "Insert into ChatGPT" }),
    );
    expect(mocks.copy).toHaveBeenCalledWith(output.prompt);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "copied to clipboard",
    );
  });
  it("does not make a pairing call or request host access until the user consents and connects", async () => {
    mocks.read.mockResolvedValue({});
    const user = userEvent.setup();
    render(<App />);
    await user.type(
      await screen.findByLabelText("API server address"),
      "https://workspace.example.com",
    );
    expect(
      screen.getByRole("button", { name: "Connect workspace" }),
    ).toBeDisabled();
    expect(mocks.request).not.toHaveBeenCalled();
    expect(mocks.permission).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Connect workspace" }));
    expect(mocks.permission).toHaveBeenCalledWith({
      origins: ["https://workspace.example.com/*"],
    });
    expect(mocks.write).toHaveBeenCalledWith({
      settings: expect.objectContaining({
        apiOrigin: "https://workspace.example.com",
        consent: true,
      }),
    });
    expect(
      await screen.findByRole("button", { name: "Create pairing code" }),
    ).toBeInTheDocument();
    expect(mocks.request).not.toHaveBeenCalled();
  });
});
