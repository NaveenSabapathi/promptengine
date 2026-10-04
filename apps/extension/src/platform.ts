import browser from "webextension-polyfill";
export default browser;
// Chrome defaults local storage to also be accessible to content scripts. Lock it down
// when the browser supports access levels. Injected adapter code never calls storage.
export async function protectStorage() {
  const local = browser.storage.local as unknown as {
    setAccessLevel?: (options: {
      accessLevel: "TRUSTED_CONTEXTS";
    }) => Promise<void>;
  };
  if (typeof local.setAccessLevel === "function")
    await local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
}
