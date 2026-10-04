import fs from "node:fs";
import path from "node:path";
const name = "PromptEngine";
const shared = {
  name,
  version: "0.1.0",
  description:
    "Craft prompts in your paired workspace. Insert plain text into ChatGPT, Claude or Gemini without sending.",
  icons: {
    32: "icons/icon-32.png",
    48: "icons/icon-48.png",
    128: "icons/icon-128.png",
  },
  permissions: ["storage", "activeTab", "clipboardWrite"],
};
const popup = {
  default_popup: "popup.html",
  default_title: name,
  default_icon: shared.icons,
};
const hosts = ["https://*/*", "http://localhost/*", "http://127.0.0.1/*"];
const gecko = {
  id: "promptengine@naveensabapathi.github.io",
  strict_min_version: "140.0",
  data_collection_permissions: {
    required: ["authenticationInfo", "personalCommunications"],
  },
};
for (const target of ["chrome", "firefox", "firefox-mv2"]) {
  const manifest =
    target === "firefox-mv2"
      ? {
          ...shared,
          manifest_version: 2,
          browser_action: popup,
          background: { scripts: ["background.js"], persistent: false },
          optional_permissions: hosts,
          browser_specific_settings: {
            gecko,
            gecko_android: { strict_min_version: "142.0" },
          },
          content_security_policy:
            "script-src 'self'; object-src 'self'; base-uri 'none'",
        }
      : {
          ...shared,
          manifest_version: 3,
          action: popup,
          background:
            target === "chrome"
              ? { service_worker: "background.js" }
              : { scripts: ["background.js"] },
          permissions: [...shared.permissions, "scripting"],
          optional_host_permissions: hosts,
          content_security_policy: {
            extension_pages:
              "script-src 'self'; object-src 'self'; base-uri 'none'",
          },
          ...(target === "firefox"
            ? {
                browser_specific_settings: {
                  gecko,
                  gecko_android: { strict_min_version: "142.0" },
                },
              }
            : { minimum_chrome_version: "114" }),
        };
  const dir = path.resolve("dist", target);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.cpSync("dist/ui", dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
}
console.log("Packaged Chrome MV3, Firefox MV3, and Firefox MV2 directories.");
