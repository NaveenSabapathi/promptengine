import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
import ts from "typescript";
import { chromium } from "@playwright/test";
const source = fs.readFileSync(
  new URL("../src/adapter.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
  },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(compiled, sandbox);
const adapter = sandbox.exports.insertPrompt.toString();
const browser = await chromium.launch({
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
    : {}),
  headless: true,
  args: ["--no-sandbox", "--no-zygote"],
});
const context = await browser.newContext();
let checked = 0;
try {
  for (const [origin, markup] of [
    [
      "https://chatgpt.com",
      '<textarea id="prompt-textarea" aria-label="Prompt"></textarea>',
    ],
    [
      "https://chatgpt.com",
      '<div id="prompt-textarea" contenteditable="true" role="textbox" aria-label="Prompt"></div>',
    ],
    [
      "https://claude.ai",
      '<div class="ProseMirror" contenteditable="true" role="textbox" aria-label="Prompt"></div>',
    ],
    [
      "https://gemini.google.com",
      '<rich-textarea><div class="ql-editor" contenteditable="true" role="textbox" aria-label="Prompt"></div></rich-textarea>',
    ],
  ]) {
    const page = await context.newPage();
    await page.route(origin + "/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: `<!doctype html><html lang="en"><head><title>Composer fixture</title><style>textarea,[contenteditable]{display:block;width:400px;min-height:100px;white-space:pre-wrap}</style></head><body><form>${markup}<button type="submit">Send</button></form><script>window.sent=0;window.inputs=0;window.keys=0;document.querySelector('form').addEventListener('submit',event=>{event.preventDefault();window.sent++});document.addEventListener('input',()=>window.inputs++);document.addEventListener('keydown',()=>window.keys++);</script></body></html>`,
      }),
    );
    await page.goto(origin + "/");
    const prompt =
      "First line\nSecond line <script>window.sent=999</script> & plain text.";
    const insert = (text, replace = false) =>
      page.evaluate(`(${adapter})(${JSON.stringify(text)},${replace});`);
    const result = await insert(prompt);
    assert.equal(result.status, "inserted", JSON.stringify(result));
    const state = await page.evaluate(() => {
      const editor = document.querySelector("textarea,[contenteditable]");
      return {
        text: editor.value ?? editor.innerText,
        script: editor.querySelector("script") !== null,
        sent: window.sent,
        inputs: window.inputs,
        keys: window.keys,
      };
    });
    assert.equal(state.text, prompt);
    assert.equal(state.script, false);
    assert.equal(state.sent, 0);
    assert.equal(state.keys, 0);
    assert.ok(state.inputs > 0);
    assert.equal((await insert("Replacement")).status, "occupied");
    assert.equal((await insert("Replacement", true)).status, "inserted");
    assert.equal(await page.evaluate(() => window.sent), 0);
    checked++;
    await page.close();
  }
  const page = await context.newPage();
  await page.route("https://example.com/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: '<textarea id="prompt-textarea"></textarea>',
    }),
  );
  await page.goto("https://example.com");
  assert.equal(
    (await page.evaluate(`(${adapter})("Prompt",false);`)).status,
    "unsupported",
  );
  checked++;
  await page.close();
  console.log(
    `${checked} native Chromium adapter fixtures passed. No chat service was contacted.`,
  );
} finally {
  await browser.close();
}
