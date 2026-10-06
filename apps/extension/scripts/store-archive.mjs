import fs from "node:fs";
import { execFileSync } from "node:child_process";
if (process.env.EXTENSION_DEVELOPMENT === "true")
  throw new Error("Development packages cannot be released");
fs.mkdirSync("dist/store", { recursive: true });
for (const target of ["chrome", "firefox", "firefox-mv2"]) {
  const manifest = JSON.parse(
    fs.readFileSync(`dist/${target}/manifest.json`, "utf8"),
  );
  const hosts =
    manifest.optional_host_permissions || manifest.optional_permissions;
  if (JSON.stringify(hosts) !== JSON.stringify(["https://promptlogic.io/*"]))
    throw new Error(
      "Release host permissions must be limited to promptlogic.io",
    );
  const archive = `dist/store/promptlogic-${target}-${manifest.version}.zip`;
  if (fs.existsSync(archive)) fs.unlinkSync(archive);
  execFileSync(
    "zip",
    ["-qr", `../store/promptlogic-${target}-${manifest.version}.zip`, "."],
    { cwd: `dist/${target}` },
  );
}
console.log("Store archives created with production-only host permissions.");
