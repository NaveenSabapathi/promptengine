export interface InsertResult {
  status:
    | "inserted"
    | "unsupported"
    | "missing"
    | "ambiguous"
    | "occupied"
    | "blocked"
    | "failed";
  site?: string;
  message: string;
}
export function supportedSite(value: string) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return null;
    return (
      (
        {
          "chatgpt.com": "ChatGPT",
          "chat.openai.com": "ChatGPT",
          "claude.ai": "Claude",
          "gemini.google.com": "Gemini",
        } as Record<string, string>
      )[url.hostname] || null
    );
  } catch {
    return null;
  }
}
// This function is serialized by the WebExtension API. Keep ALL runtime dependencies
// inside its body. Its only inputs are prompt text and an explicit replace decision.
export function insertPrompt(text: string, replace = false): InsertResult {
  const host = window.location.hostname;
  const site = (
    {
      "chatgpt.com": "ChatGPT",
      "chat.openai.com": "ChatGPT",
      "claude.ai": "Claude",
      "gemini.google.com": "Gemini",
    } as Record<string, string>
  )[host];
  if (window.location.protocol !== "https:" || !site)
    return {
      status: "unsupported",
      message: "This page does not have a supported chat editor.",
    };
  if (typeof text !== "string" || !text.trim() || text.length > 50000)
    return {
      status: "blocked",
      site,
      message: "The prompt is empty or too large to insert.",
    };
  const selectors =
    site === "ChatGPT"
      ? [
          "textarea#prompt-textarea",
          '#prompt-textarea[contenteditable="true"]',
          'textarea[data-testid="prompt-textarea"]',
        ]
      : site === "Claude"
        ? [
            '[contenteditable="true"].ProseMirror',
            '[contenteditable="true"][role="textbox"][data-placeholder]',
            'textarea[aria-label="Write your prompt to Claude"]',
          ]
        : [
            'rich-textarea .ql-editor[contenteditable="true"]',
            'rich-textarea [contenteditable="true"][role="textbox"]',
            'textarea[aria-label="Enter a prompt here"]',
          ];
  const found = new Set<HTMLElement>();
  for (const selector of selectors) {
    for (const node of document.querySelectorAll<HTMLElement>(selector)) {
      const style = getComputedStyle(node);
      if (
        node.getClientRects().length &&
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        !node.closest('[inert],[aria-hidden="true"]') &&
        !node.hasAttribute("disabled") &&
        !node.hasAttribute("readonly") &&
        node.getAttribute("aria-disabled") !== "true"
      )
        found.add(node);
    }
  }
  const candidates = [...found];
  if (!candidates.length)
    return {
      status: "missing",
      site,
      message: `No editable ${site} composer was found. Copy the prompt instead.`,
    };
  if (candidates.length !== 1)
    return {
      status: "ambiguous",
      site,
      message:
        "Several editors were found. Copy the prompt into the intended chat.",
    };
  const editor = candidates[0];
  const textarea = editor instanceof HTMLTextAreaElement;
  const existing = textarea ? editor.value : editor.textContent || "";
  if (existing.trim() && !replace)
    return {
      status: "occupied",
      site,
      message:
        "The chat already has a draft. Replace it only if you are ready to discard it.",
    };
  const before = new InputEvent("beforeinput", {
    bubbles: true,
    cancelable: true,
    inputType: "insertText",
    data: text,
  });
  if (!editor.dispatchEvent(before))
    return {
      status: "blocked",
      site,
      message: "The chat editor declined the change. Copy the prompt instead.",
    };
  try {
    editor.focus();
    if (textarea) {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      if (!setter)
        return {
          status: "failed",
          site,
          message: "The editor cannot accept text. Copy the prompt instead.",
        };
      setter.call(editor, text);
    } else {
      const selection = window.getSelection();
      if (!selection)
        return {
          status: "failed",
          site,
          message:
            "The editor cannot accept a selection. Copy the prompt instead.",
        };
      const range = document.createRange();
      range.selectNodeContents(editor);
      selection.removeAllRanges();
      selection.addRange(range);
      // Native text editing gives ProseMirror/Quill an actual editing operation.
      // No HTML, keys, clipboard read, form submission, or Send button is used.
      if (!document.execCommand("insertText", false, text))
        return {
          status: "failed",
          site,
          message:
            "Native text insertion is unavailable. Copy the prompt instead.",
        };
    }
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: text,
      }),
    );
    if (textarea) editor.dispatchEvent(new Event("change", { bubbles: true }));
    const actual = textarea
      ? editor.value
      : editor.innerText || editor.textContent || "";
    if (actual.replace(/\r\n/g, "\n") !== text.replace(/\r\n/g, "\n"))
      return {
        status: "failed",
        site,
        message:
          "The editor did not preserve the full prompt. Use Copy and paste manually.",
      };
    return {
      status: "inserted",
      site,
      message: `Inserted into ${site}. Review it in the chat; Send has not been clicked.`,
    };
  } catch {
    return {
      status: "failed",
      site,
      message:
        "The editor changed or rejected insertion. Copy the prompt instead.",
    };
  }
}
