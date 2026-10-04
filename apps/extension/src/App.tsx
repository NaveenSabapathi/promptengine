import {
  useEffect,
  useState,
  type FormEvent,
  type ComponentProps,
} from "react";
import {
  Terminal,
  Settings2,
  ArrowUpRight,
  Copy,
  Check,
  Sparkles,
  Unplug,
  Expand,
  RefreshCw,
  ChevronDown,
  Save,
} from "lucide-react";
import type {
  ExtensionAccess,
  PairingRequest,
  PresetList,
  Preset,
  PresetId,
  PromptTone,
  CompileMode,
  GenerationEngine,
  GenerationResponse,
  Usage,
} from "@promptengine/shared-types";
import browser from "./platform";
import {
  readStored,
  setStored,
  clearAuth,
  editorState,
  saveEditor,
  normalizeOrigin,
  hostPermission,
  approvalURL,
  type Settings,
} from "./storage";
import { request, ExtensionError, errorText } from "./api";
import { copyPrompt, insertIntoTab } from "./insert";
import { supportedSite } from "./adapter";
function Button({ className = "", ...props }: ComponentProps<"button">) {
  return <button className={`button ${className}`} {...props} />;
}
function Notice({ error, message }: { error: string; message: string }) {
  return error ? (
    <div className="notice error" role="alert">
      {error}
    </div>
  ) : message ? (
    <div className="notice success" role="status">
      {message}
    </div>
  ) : null;
}
export default function App() {
  const [ready, setReady] = useState(false);
  const [settings, setSettings] = useState<Settings>();
  const [auth, setAuth] = useState<ExtensionAccess>();
  const [pairing, setPairing] = useState<PairingRequest>();
  const [configure, setConfigure] = useState(false);
  const [apiOrigin, setApiOrigin] = useState("");
  const [webOrigin, setWebOrigin] = useState("");
  const [deviceName, setDeviceName] = useState("My browser");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [catalog, setCatalog] = useState<PresetList>();
  const [custom, setCustom] = useState<Preset[]>([]);
  const [usage, setUsage] = useState<Usage>();
  const [aiEnabled, setAiEnabled] = useState(false);
  const [raw, setRaw] = useState("");
  const [preset, setPreset] = useState<PresetId>("coding");
  const [tone, setTone] = useState<PromptTone>("professional");
  const [mode, setMode] = useState<CompileMode>("Build");
  const [engine, setEngine] = useState<GenerationEngine>("local");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [result, setResult] = useState<GenerationResponse>();
  const [advanced, setAdvanced] = useState(false);
  const [tabId, setTabId] = useState<number>();
  const [site, setSite] = useState<string | null>(null);
  const [replace, setReplace] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    let alive = true;
    void (async () => {
      try {
        const stored = await readStored();
        if (!alive) return;
        setSettings(stored.settings);
        setApiOrigin(stored.settings?.apiOrigin || "");
        setWebOrigin(stored.settings?.webOrigin || "");
        setDeviceName(stored.settings?.deviceName || "My browser");
        setConsent(Boolean(stored.settings?.consent));
        setPairing(stored.pairing);
        if (
          stored.auth &&
          new Date(stored.auth.expires_at).getTime() > Date.now()
        ) {
          const saved = await editorState(stored.auth.token_id);
          if (saved) {
            setRaw(saved.raw);
            setPreset(saved.preset);
            setTone(saved.tone);
            setMode(saved.mode);
            setEngine(saved.engine);
            setFields(saved.fields);
            setResult(saved.result);
          }
          setAuth(stored.auth);
        } else if (stored.auth) {
          await clearAuth();
          setMessage("Your browser access expired. Pair it again.");
        }
        const target = new URLSearchParams(location.search).get("target");
        const id =
          target && /^\d+$/.test(target)
            ? Number(target)
            : (
                await browser.tabs.query({ active: true, currentWindow: true })
              )[0]?.id;
        setTabId(id);
        if (id !== undefined) {
          const tab = await browser.tabs.get(id);
          setSite(supportedSite(tab.url || ""));
        }
      } catch (e) {
        setError(errorText(e));
      } finally {
        if (alive) setReady(true);
      }
    })();
    const expired = () => {
      setAuth(undefined);
      setResult(undefined);
      setRaw("");
      setCatalog(undefined);
      setFields({});
      setCustom([]);
      setConfigure(false);
    };
    window.addEventListener("extension-expired", expired);
    return () => {
      alive = false;
      clearInterval(timer);
      window.removeEventListener("extension-expired", expired);
    };
  }, []);
  useEffect(() => {
    if (auth) void load();
  }, [auth?.token_id]);
  useEffect(() => {
    if (!ready || !auth) return;
    const timer = setTimeout(
      () =>
        void saveEditor({
          owner: auth.token_id,
          raw,
          preset,
          tone,
          mode,
          engine,
          fields,
          result,
        }).catch((e) => setError(errorText(e))),
      150,
    );
    return () => clearTimeout(timer);
  }, [ready, auth?.token_id, raw, preset, tone, mode, engine, fields, result]);
  async function load() {
    try {
      const [p, u, c] = await Promise.all([
        request<PresetList>("/api/presets"),
        request<Usage>("/api/usage"),
        request<{ ai_enabled: boolean }>("/api/auth/capabilities"),
      ]);
      setCatalog(p);
      setUsage(u);
      setAiEnabled(c.ai_enabled);
      try {
        setCustom(
          (await request<{ presets: Preset[] }>("/api/custom-presets")).presets,
        );
      } catch (e) {
        if (e instanceof ExtensionError && e.code === "pro_required") {
          setCustom([]);
          if (preset.startsWith("custom_")) {
            setPreset("coding");
            setFields({});
          }
        } else throw e;
      }
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function configureServer(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const next: Settings = {
        apiOrigin: normalizeOrigin(apiOrigin),
        webOrigin: normalizeOrigin(webOrigin || apiOrigin),
        deviceName: deviceName.trim(),
        consent: true,
      };
      if (!consent)
        throw new Error("Review and accept the data notice to connect.");
      if (!next.deviceName || next.deviceName.length > 80)
        throw new Error("Use a device name of 1–80 characters.");
      // The permission prompt must be the first asynchronous browser action in this
      // user-initiated handler. Never ask for all hosts at installation.
      if (
        !(await browser.permissions.request({
          origins: [hostPermission(next.apiOrigin)],
        }))
      )
        throw new Error(
          "Workspace access was declined. You can try again when ready.",
        );
      const previous = (await readStored()).settings;
      const changed =
        previous?.apiOrigin !== next.apiOrigin ||
        previous?.webOrigin !== next.webOrigin;
      if (changed) {
        await clearAuth();
        setAuth(undefined);
        setPairing(undefined);
        setResult(undefined);
        setRaw("");
        setFields({});
        setPreset("coding");
      }
      await setStored({ settings: next });
      setSettings(next);
      setApiOrigin(next.apiOrigin);
      setWebOrigin(next.webOrigin);
      setConfigure(false);
      if (
        previous &&
        hostPermission(previous.apiOrigin) !== hostPermission(next.apiOrigin)
      )
        await browser.permissions.remove({
          origins: [hostPermission(previous.apiOrigin)],
        });
      setMessage("Workspace connected. Pair this browser to continue.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function createPairing() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const p = await request<PairingRequest>("/api/extension/pairing", {
        device_name: settings?.deviceName,
      });
      if (!settings) throw new Error("Workspace is missing.");
      approvalURL(p.approval_url, settings);
      await setStored({ pairing: p });
      setPairing(p);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function openApproval() {
    if (!pairing || !settings) return;
    try {
      await browser.tabs.create({
        url: approvalURL(pairing.approval_url, settings),
      });
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function exchange() {
    if (!pairing) return;
    setBusy(true);
    setError("");
    try {
      const token = await request<ExtensionAccess>(
        "/api/extension/pairing/exchange",
        {
          pairing_id: pairing.pairing_id,
          code: pairing.code,
          device_secret: pairing.device_secret,
        },
      );
      if (
        !token.access_token.startsWith("pe_ext_") ||
        token.token_type !== "Bearer" ||
        !token.scopes.includes("refine")
      )
        throw new Error("The server returned invalid browser access.");
      await setStored({ auth: token });
      await browser.storage.local.remove("pairing");
      setPairing(undefined);
      setAuth(token);
      setMessage("Browser paired. Your workspace is ready.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    setError("");
    let revoked = false;
    try {
      await request("/api/extension/disconnect", {});
      revoked = true;
    } catch (e) {
      setError(errorText(e));
    } finally {
      await clearAuth();
      setAuth(undefined);
      setPairing(undefined);
      setResult(undefined);
      setRaw("");
      setFields({});
      setDisconnectOpen(false);
      setConfigure(false);
      setBusy(false);
      setMessage(
        revoked
          ? "Browser access revoked and local session cleared."
          : "Local access cleared. If the server was unavailable, revoke this browser from web Settings.",
      );
    }
  }
  const selected = [...(catalog?.presets || []), ...custom].find(
    (p) => p.id === preset,
  );
  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    setResult(undefined);
    setReplace(false);
    setSaveOpen(false);
    try {
      if (!auth) throw new Error("Pair this browser again.");
      await saveEditor({
        owner: auth.token_id,
        raw,
        preset,
        tone,
        mode,
        engine,
        fields,
      });
      const output = await request<GenerationResponse>(
        engine === "ai" ? "/api/refine" : "/api/compile",
        {
          raw_input: raw,
          preset,
          tone,
          mode,
          fields: Object.fromEntries(
            Object.entries(fields).filter(([, v]) => v.trim()),
          ),
        },
      );
      setResult(output);
      setTitle(selected?.name + " prompt");
      await saveEditor({
        owner: auth.token_id,
        raw,
        preset,
        tone,
        mode,
        engine,
        fields,
        result: output,
      });
      setUsage(await request<Usage>("/api/usage"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function copy(value = result?.prompt) {
    if (!value) return;
    try {
      await copyPrompt(value);
      setMessage("Copied to clipboard. Paste it when you are ready.");
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function insert(approvedReplace = false) {
    if (!result) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const answer = await insertIntoTab(tabId, result.prompt, approvedReplace);
      if (answer.status === "occupied") {
        setReplace(true);
        setMessage(answer.message);
      } else if (answer.status === "inserted") {
        setReplace(false);
        setMessage(answer.message);
      } else {
        await copyPrompt(result.prompt);
        setReplace(false);
        setMessage(
          answer.message + " The prompt has been copied to clipboard.",
        );
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!result) return;
    setBusy(true);
    setError("");
    try {
      await request("/api/prompts", {
        title,
        content: result.prompt,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      setSaveOpen(false);
      setMessage("Prompt saved to your web library.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function openWeb(path = "/workspace") {
    if (!settings) return;
    try {
      await browser.tabs.create({ url: settings.webOrigin + path });
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function expand() {
    try {
      await browser.tabs.create({
        url:
          browser.runtime.getURL("popup.html") +
          (tabId !== undefined ? "?target=" + tabId : ""),
      });
    } catch (e) {
      setError(errorText(e));
    }
  }
  const seconds = pairing
    ? Math.max(
        0,
        Math.ceil((new Date(pairing.expires_at).getTime() - clock) / 1000),
      )
    : 0;
  if (!ready)
    return (
      <main className="boot" role="status">
        Opening your prompt workspace…
      </main>
    );
  return (
    <div className="extension">
      <header>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            void openWeb();
          }}
        >
          <span>
            <Terminal size={18} />
          </span>
          PromptEngine<small>BETA</small>
        </a>
        <div>
          <Button
            className="icon ghost"
            aria-label="Open editor in a tab"
            disabled={busy}
            onClick={() => void expand()}
          >
            <Expand size={16} />
          </Button>
          <Button
            className="icon ghost"
            aria-label="Workspace settings"
            disabled={busy}
            onClick={() => setConfigure(!configure)}
          >
            <Settings2 size={16} />
          </Button>
        </div>
      </header>
      <main>
        <Notice error={error} message={message} />
        {!settings || configure ? (
          <section className="setup">
            <span className="eyebrow">YOUR WORKSPACE, WITHIN REACH</span>
            <h1>Connect your workspace.</h1>
            <p>
              Use your PromptEngine server address. No API key or account
              password belongs in this extension.
            </p>
            <form onSubmit={(e) => void configureServer(e)}>
              <label htmlFor="api-origin">API server address</label>
              <input
                id="api-origin"
                type="url"
                required
                value={apiOrigin}
                onChange={(e) => setApiOrigin(e.target.value)}
                placeholder="https://your-workspace.com"
              />
              <label htmlFor="web-origin">
                Web app address <small>Leave blank if the same</small>
              </label>
              <input
                id="web-origin"
                type="url"
                value={webOrigin}
                onChange={(e) => setWebOrigin(e.target.value)}
                placeholder="https://your-workspace.com"
              />
              <label htmlFor="device-name">Browser name</label>
              <input
                id="device-name"
                required
                maxLength={80}
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
              />
              <div className="data-notice">
                <Check size={17} />
                <p>
                  Pairing information and prompts you submit go to this server.
                  AI refinement also sends your task to its AI provider. Only
                  Save stores prompt content in your account. No chat history or
                  browsing history is sent.
                </p>
              </div>
              <label className="consent">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  required
                />
                I understand and allow this workspace connection.
              </label>
              <Button type="submit" disabled={busy || !consent}>
                {busy ? "Connecting…" : "Connect workspace"}
                <ArrowUpRight size={16} />
              </Button>
              {settings && (
                <Button
                  className="ghost"
                  type="button"
                  disabled={busy}
                  onClick={() => setConfigure(false)}
                >
                  Back to editor
                </Button>
              )}
            </form>
            {auth && (
              <div className="disconnect">
                <Button
                  className="outline"
                  disabled={busy}
                  onClick={() => setDisconnectOpen(true)}
                >
                  <Unplug size={15} />
                  Disconnect this browser
                </Button>
              </div>
            )}
          </section>
        ) : !auth ? (
          <section className="pairing">
            <span className="eyebrow">ONE BROWSER. YOUR WORKSPACE.</span>
            <h1>Pair this browser.</h1>
            <p>
              Approve a short-lived code in your web account. Your account
              password stays in the web app.
            </p>
            {pairing ? (
              <>
                <span className="code-label">YOUR PAIRING CODE</span>
                <div className="pairing-code">
                  {pairing.code}
                  <Button
                    className="icon ghost"
                    aria-label="Copy pairing code"
                    onClick={() => void copy(pairing.code)}
                  >
                    <Copy size={16} />
                  </Button>
                </div>
                <span className="expires">
                  {seconds
                    ? `Expires in ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
                    : "This code has expired."}
                </span>
                <ol>
                  <li>Open the web app and sign in.</li>
                  <li>Review this browser and approve the code.</li>
                  <li>Reopen this extension and complete pairing.</li>
                </ol>
                <Button
                  disabled={busy || !seconds}
                  onClick={() => void openApproval()}
                >
                  Open approval page
                  <ArrowUpRight size={16} />
                </Button>
                <Button
                  className="outline"
                  disabled={busy || !seconds}
                  onClick={() => void exchange()}
                >
                  {busy ? "Checking…" : "I approved this browser"}
                  <Check size={16} />
                </Button>
                <Button
                  className="ghost"
                  disabled={busy}
                  onClick={() => void createPairing()}
                >
                  Create a new code
                </Button>
              </>
            ) : (
              <Button disabled={busy} onClick={() => void createPairing()}>
                {busy ? "Creating…" : "Create pairing code"}
                <ArrowUpRight size={16} />
              </Button>
            )}
            <span className="pairing-server">{settings.apiOrigin}</span>
          </section>
        ) : (
          <>
            <div className="workspace-heading">
              <div>
                <span className="eyebrow">CLARITY BEFORE EXECUTION</span>
                <h1>A better starting point.</h1>
              </div>
              {usage && (
                <span className="quota">
                  <Sparkles size={12} />
                  {usage.remaining}/{usage.daily_ai_limit} AI left
                </span>
              )}
            </div>
            {!catalog ? (
              <div className="retry">
                <p>Load your workspace to begin.</p>
                <Button className="outline" onClick={() => void load()}>
                  <RefreshCw size={14} />
                  Load presets
                </Button>
              </div>
            ) : (
              <form onSubmit={(e) => void generate(e)}>
                <label htmlFor="preset">Preset</label>
                <select
                  id="preset"
                  disabled={busy}
                  value={preset}
                  onChange={(e) => {
                    setPreset(e.target.value as PresetId);
                    setFields({});
                  }}
                >
                  {catalog.presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                  {custom.length > 0 && (
                    <optgroup label="Your presets">
                      {custom.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                <label htmlFor="raw-input">
                  What do you want to accomplish?
                </label>
                <textarea
                  id="raw-input"
                  required
                  maxLength={20000}
                  disabled={busy}
                  value={raw}
                  onChange={(e) => setRaw(e.target.value)}
                  placeholder="The task, the audience, and what a good result looks like…"
                  className="raw-input"
                />
                <div className="character-count">
                  {raw.length.toLocaleString()} / 20,000
                </div>
                <div className="field-row">
                  <div>
                    <label htmlFor="tone">Tone</label>
                    <select
                      id="tone"
                      disabled={busy}
                      value={tone}
                      onChange={(e) => setTone(e.target.value as PromptTone)}
                    >
                      {catalog.tones.map((t) => (
                        <option key={t} value={t}>
                          {t[0].toUpperCase() + t.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="mode">Mode</label>
                    <select
                      id="mode"
                      disabled={busy}
                      value={mode}
                      onChange={(e) => setMode(e.target.value as CompileMode)}
                    >
                      {catalog.modes.map((m) => (
                        <option key={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <Button
                  className="disclosure ghost"
                  type="button"
                  aria-expanded={advanced}
                  aria-controls="preset-fields"
                  onClick={() => setAdvanced(!advanced)}
                >
                  Add context & constraints
                  <ChevronDown size={14} />
                </Button>
                {advanced && (
                  <div id="preset-fields">
                    {Object.entries({
                      ...selected?.required_fields,
                      ...selected?.optional_fields,
                    }).map(([key, label]) => (
                      <div key={key}>
                        <label htmlFor={"field-" + key}>
                          {key.replaceAll("_", " ")}
                        </label>
                        <input
                          id={"field-" + key}
                          disabled={busy}
                          maxLength={4000}
                          value={fields[key] || ""}
                          onChange={(e) =>
                            setFields({ ...fields, [key]: e.target.value })
                          }
                          placeholder={label}
                        />
                      </div>
                    ))}
                  </div>
                )}
                <label htmlFor="engine">Generation method</label>
                <select
                  id="engine"
                  disabled={busy}
                  value={engine}
                  onChange={(e) =>
                    setEngine(e.target.value as GenerationEngine)
                  }
                >
                  <option value="local">
                    Local compiler · no AI quota used
                  </option>
                  <option value="ai" disabled={!aiEnabled}>
                    AI refinement {!aiEnabled ? "· not configured" : ""}
                  </option>
                </select>
                <div className="generate">
                  <Button
                    type="submit"
                    disabled={
                      busy ||
                      !raw.trim() ||
                      (engine === "ai" && (!aiEnabled || !usage?.remaining))
                    }
                  >
                    <Sparkles size={15} />
                    {busy
                      ? "Please wait…"
                      : engine === "ai"
                        ? "Refine with AI"
                        : "Build prompt"}
                    <ArrowUpRight size={15} />
                  </Button>
                </div>
                <p className="keep-open">
                  Keep this popup open while generating, or use the tab editor
                  above.
                </p>
              </form>
            )}
            {result && (
              <section className="output">
                <div className="output-heading">
                  <h2>Your crafted prompt</h2>
                  <span className="ready">
                    <Check size={12} />
                    READY
                  </span>
                </div>
                <div className="metrics">
                  <div>
                    <span>Input tokens</span>
                    <strong>
                      {result.metrics.raw_tokens.toLocaleString()}
                    </strong>
                  </div>
                  <div>
                    <span>Output tokens</span>
                    <strong>
                      {result.metrics.generated_tokens.toLocaleString()}
                    </strong>
                  </div>
                  <div>
                    <span>
                      {result.metrics.is_reduction ? "Reduced" : "Added"}
                    </span>
                    <strong>
                      {Math.abs(
                        result.metrics.token_difference,
                      ).toLocaleString()}
                    </strong>
                  </div>
                </div>
                <p className="token-note">
                  GPT-4o-mini text counts. Other models differ. Structure can
                  add tokens.
                </p>
                <label htmlFor="generated-prompt" className="sr-only">
                  Generated prompt
                </label>
                <textarea
                  id="generated-prompt"
                  readOnly
                  value={result.prompt}
                  className="generated-prompt"
                />
                {result.clarification_questions.length > 0 && (
                  <details className="clarifications" open>
                    <summary>Worth clarifying</summary>
                    <ul>
                      {result.clarification_questions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {result.assumptions.length > 0 && (
                  <details className="clarifications">
                    <summary>Assumptions</summary>
                    <ul>
                      {result.assumptions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="output-actions">
                  <Button disabled={busy} onClick={() => void insert()}>
                    <ArrowUpRight size={15} />
                    {site ? `Insert into ${site}` : "Copy for this tab"}
                  </Button>
                  <Button
                    className="outline"
                    disabled={busy}
                    onClick={() => void copy()}
                  >
                    <Copy size={15} />
                    Copy
                  </Button>
                  <Button
                    className="icon outline"
                    aria-label="Save to library"
                    disabled={busy}
                    onClick={() => setSaveOpen(!saveOpen)}
                  >
                    <Save size={16} />
                  </Button>
                </div>
                {replace && (
                  <div
                    className="confirmation"
                    role="alertdialog"
                    aria-labelledby="replace-title"
                  >
                    <h3 id="replace-title">Replace the existing chat draft?</h3>
                    <p>
                      The draft currently in the chat will be discarded. Nothing
                      will be sent.
                    </p>
                    <div>
                      <Button disabled={busy} onClick={() => void insert(true)}>
                        Replace draft
                      </Button>
                      <Button
                        className="outline"
                        disabled={busy}
                        onClick={() => {
                          setReplace(false);
                          void copy();
                        }}
                      >
                        Keep draft & copy
                      </Button>
                    </div>
                  </div>
                )}
                {saveOpen && (
                  <form onSubmit={(e) => void save(e)}>
                    <label htmlFor="save-title">Prompt title</label>
                    <input
                      id="save-title"
                      required
                      maxLength={200}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                    <label htmlFor="save-tags">
                      Tags <small>Comma separated</small>
                    </label>
                    <input
                      id="save-tags"
                      value={tags}
                      onChange={(e) => setTags(e.target.value)}
                    />
                    <Button type="submit" disabled={busy}>
                      {busy ? "Saving…" : "Save prompt"}
                    </Button>
                  </form>
                )}
                <p className="insert-note">
                  Plain text only. Review in the chat before sending.
                </p>
              </section>
            )}
          </>
        )}
        {disconnectOpen && (
          <div
            className="confirmation"
            role="alertdialog"
            aria-labelledby="disconnect-title"
          >
            <h3 id="disconnect-title">Disconnect this browser?</h3>
            <p>Its scoped access will be revoked and local drafts cleared.</p>
            <div>
              <Button disabled={busy} onClick={() => void disconnect()}>
                Confirm disconnect
              </Button>
              <Button
                className="outline"
                disabled={busy}
                onClick={() => setDisconnectOpen(false)}
              >
                Keep connected
              </Button>
            </div>
          </div>
        )}
      </main>
      <footer>
        <span>
          <span className="status-dot" />
          {auth ? "Paired workspace" : "Secure browser pairing"}
        </span>
        <Button
          className="ghost"
          disabled={busy || !settings}
          onClick={() => void openWeb(auth ? "/history" : "/workspace")}
        >
          Open web app
          <ArrowUpRight size={12} />
        </Button>
      </footer>
    </div>
  );
}
