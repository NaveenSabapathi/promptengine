import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { render, act, screen } from "@testing-library/react";
import { useState } from "react";
import { insertPrompt, supportedSite } from "./adapter";
const originalWindow = window;
function host(name: string, protocol = "https:") {
  vi.stubGlobal("window", {
    location: { hostname: name, protocol },
    getSelection: () => originalWindow.getSelection(),
  });
}
beforeEach(() => {
  host("chatgpt.com");
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    { width: 300, height: 100 },
  ] as unknown as DOMRectList);
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});
describe("safe host detection", () => {
  it("requires exact HTTPS service hosts", () => {
    for (const url of [
      "https://chatgpt.com/c/a",
      "https://chat.openai.com/",
      "https://claude.ai/new",
      "https://gemini.google.com/app",
    ])
      expect(supportedSite(url)).toBeTruthy();
    for (const url of [
      "http://chatgpt.com/",
      "https://chatgpt.com.evil.com/",
      "https://evil.com/?chatgpt.com",
      "chrome://extensions/",
    ])
      expect(supportedSite(url)).toBeNull();
  });
});
describe("composer insertion", () => {
  it("updates an actual controlled React textarea, preserving plain text and never sending", () => {
    const send = vi.fn();
    function Chat() {
      const [value, setValue] = useState("");
      return (
        <form onSubmit={send}>
          <textarea
            id="prompt-textarea"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <output data-testid="state">{value}</output>
          <button type="submit">Send</button>
        </form>
      );
    }
    render(<Chat />);
    const click = vi.spyOn(HTMLButtonElement.prototype, "click");
    const prompt =
      'Line one\n<script>alert("hello")</script> & <b>plain text</b>';
    let result;
    act(() => {
      result = insertPrompt(prompt);
    });
    expect(result).toMatchObject({ status: "inserted", site: "ChatGPT" });
    expect(screen.getByTestId("state")).toHaveTextContent(
      '<script>alert("hello")</script>',
    );
    expect(
      (document.querySelector("textarea") as HTMLTextAreaElement).value,
    ).toBe(prompt);
    expect(document.querySelector("script")).toBeNull();
    expect(send).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
  });
  it("protects a draft until replacement is explicitly requested", () => {
    document.body.innerHTML =
      '<textarea id="prompt-textarea">Existing draft</textarea>';
    expect(insertPrompt("New prompt").status).toBe("occupied");
    expect(
      (document.querySelector("textarea") as HTMLTextAreaElement).value,
    ).toBe("Existing draft");
    expect(insertPrompt("New prompt", true).status).toBe("inserted");
  });
  it("returns fallback states for missing, hidden, disabled and ambiguous editors", () => {
    expect(insertPrompt("Prompt").status).toBe("missing");
    document.body.innerHTML =
      '<textarea id="prompt-textarea" disabled></textarea>';
    expect(insertPrompt("Prompt").status).toBe("missing");
    document.body.innerHTML =
      '<textarea id="prompt-textarea" style="display:none"></textarea>';
    expect(insertPrompt("Prompt").status).toBe("missing");
    document.body.innerHTML =
      '<textarea id="prompt-textarea"></textarea><textarea data-testid="prompt-textarea"></textarea>';
    expect(insertPrompt("Prompt").status).toBe("ambiguous");
  });
  it("respects cancelled beforeinput and emits no keyboard events", () => {
    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const editor = document.querySelector("textarea")!;
    const keys = vi.fn();
    editor.addEventListener("keydown", keys);
    editor.addEventListener("beforeinput", (e) => e.preventDefault());
    expect(insertPrompt("Prompt").status).toBe("blocked");
    expect(editor.value).toBe("");
    expect(keys).not.toHaveBeenCalled();
  });
  it.each([
    ["claude.ai", '<div class="ProseMirror" contenteditable="true"></div>'],
    [
      "gemini.google.com",
      '<rich-textarea><div class="ql-editor" contenteditable="true"></div></rich-textarea>',
    ],
    ["chatgpt.com", '<div id="prompt-textarea" contenteditable="true"></div>'],
  ])("uses native text insertion for %s editors", (name, html) => {
    host(name);
    document.body.innerHTML = html;
    const command = vi.fn((_action: string, _ui: boolean, text: string) => {
      const selection = originalWindow.getSelection()!;
      selection.getRangeAt(0).deleteContents();
      selection.getRangeAt(0).insertNode(document.createTextNode(text));
      return true;
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: command,
    });
    const input = vi.fn();
    document.addEventListener("input", input, { once: true });
    expect(insertPrompt("First\nSecond <svg/onload=alert(1)>").status).toBe(
      "inserted",
    );
    expect(command).toHaveBeenCalledWith(
      "insertText",
      false,
      "First\nSecond <svg/onload=alert(1)>",
    );
    expect(input).toHaveBeenCalled();
    expect(document.querySelector("svg")).toBeNull();
  });
  it("does not pretend DOM-only editing succeeded when native editing is unavailable", () => {
    host("claude.ai");
    document.body.innerHTML =
      '<div class="ProseMirror" contenteditable="true"></div>';
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: () => false,
    });
    expect(insertPrompt("Prompt").status).toBe("failed");
    expect(document.querySelector("div")?.textContent).toBe("");
  });
  it("rechecks the host in the injected function", () => {
    host("attacker.com");
    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    expect(insertPrompt("Prompt").status).toBe("unsupported");
    expect(
      (document.querySelector("textarea") as HTMLTextAreaElement).value,
    ).toBe("");
  });
});
