// Initialize privileged storage access without loading credentials or making network calls.
// Popup initialization repeats this check before reading or writing authentication data.
const local = globalThis.chrome?.storage?.local;
if (typeof local?.setAccessLevel === "function") {
  local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {});
}
