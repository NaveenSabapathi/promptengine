import type {
  ExtensionAccess,
  PairingRequest,
  GenerationResponse,
  PresetId,
  PromptTone,
  CompileMode,
  GenerationEngine,
} from "@promptengine/shared-types";
import browser, { protectStorage } from "./platform";
export interface Settings {
  apiOrigin: string;
  webOrigin: string;
  deviceName: string;
  consent: true;
}
export interface EditorState {
  owner: string;
  raw: string;
  preset: PresetId;
  tone: PromptTone;
  mode: CompileMode;
  engine: GenerationEngine;
  fields: Record<string, string>;
  result?: GenerationResponse;
}
export interface Stored {
  settings?: Settings;
  auth?: ExtensionAccess;
  pairing?: PairingRequest;
}
export async function readStored(): Promise<Stored> {
  await protectStorage();
  return (await browser.storage.local.get([
    "settings",
    "auth",
    "pairing",
  ])) as Stored;
}
export async function setStored(value: Partial<Stored>) {
  await protectStorage();
  await browser.storage.local.set(value);
}
export async function clearAuth() {
  await browser.storage.local.remove(["auth", "pairing"]);
  await browser.storage.session.clear();
}
export async function editorState(owner: string) {
  const data = await browser.storage.session.get("editor");
  const state = data.editor as EditorState | undefined;
  return state?.owner === owner ? state : undefined;
}
export async function saveEditor(state: EditorState) {
  const stored = await readStored();
  if (stored.auth?.token_id === state.owner)
    await browser.storage.session.set({ editor: state });
}
export function normalizeOrigin(value: string) {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("Enter a valid workspace address.");
  }
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !["", "/"].includes(url.pathname)
  )
    throw new Error(
      "Use an origin only, without a path, query, or credentials.",
    );
  if (
    url.protocol !== "https:" &&
    !(
      url.protocol === "http:" &&
      ["localhost", "127.0.0.1"].includes(url.hostname)
    )
  )
    throw new Error(
      "Use HTTPS. HTTP is allowed only for localhost development.",
    );
  return url.origin;
}
export function hostPermission(origin: string) {
  const url = new URL(normalizeOrigin(origin));
  return `${url.protocol}//${url.hostname}/*`;
}
export function approvalURL(value: string, settings: Settings) {
  const url = new URL(value);
  if (
    url.origin !== settings.webOrigin ||
    url.pathname !== "/settings/extensions" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error("The server returned an unexpected approval address.");
  return url.href;
}
