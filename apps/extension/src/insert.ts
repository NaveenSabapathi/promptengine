import browser from "./platform";
import { insertPrompt, supportedSite, type InsertResult } from "./adapter";
export async function insertIntoTab(
  tabId: number | undefined,
  prompt: string,
  replace = false,
): Promise<InsertResult> {
  if (tabId === undefined)
    return {
      status: "unsupported",
      message: "No chat tab is available. Copy the prompt instead.",
    };
  try {
    const tab = await browser.tabs.get(tabId);
    if (!tab.url || !supportedSite(tab.url))
      return {
        status: "unsupported",
        message:
          "The selected tab is not a supported chat. Copy the prompt instead.",
      };
    if (browser.runtime.getManifest().manifest_version === 3) {
      const result = await browser.scripting.executeScript({
        target: { tabId },
        func: insertPrompt,
        args: [prompt, replace],
      });
      return (
        (result[0]?.result as InsertResult) || {
          status: "failed",
          message: "No insertion result was returned. Copy the prompt instead.",
        }
      );
    }
    const serialized = JSON.stringify(prompt)
      .replace(/\u2028/g, "\\u2028")
      .replace(/\u2029/g, "\\u2029");
    const result = await browser.tabs.executeScript(tabId, {
      code: `(${insertPrompt.toString()})(${serialized},${replace});`,
      runAt: "document_idle",
    });
    return result[0] as InsertResult;
  } catch {
    return {
      status: "blocked",
      message:
        "The browser did not allow access to this tab. Open the extension from that chat, or copy the prompt.",
    };
  }
}
export async function copyPrompt(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const field = document.createElement("textarea");
    field.value = text;
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    if (!copied)
      throw new Error(
        "Clipboard access failed. Select the prompt below and copy it manually.",
      );
  }
}
