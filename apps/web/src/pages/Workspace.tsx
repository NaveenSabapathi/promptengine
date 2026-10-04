import { useEffect, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import {
  ArrowUpRight,
  Copy,
  Check,
  Sparkles,
  Save,
  ChevronDown,
  LoaderCircle,
  WandSparkles,
} from "lucide-react";
import type {
  Preset,
  PresetList,
  PresetId,
  PromptTone,
  CompileMode,
  GenerationEngine,
  GenerationResponse,
  Usage,
} from "@promptengine/shared-types";
import { api, APIException, post, errorText } from "@/lib/api";
import { copyText } from "@/lib/utils";
import { Heading, Notice, Busy } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import type { Capabilities } from "./Login";
export default function Workspace() {
  const location = useLocation();
  const [catalog, setCatalog] = useState<PresetList>();
  const [custom, setCustom] = useState<Preset[]>([]);
  const [caps, setCaps] = useState<Capabilities>();
  const [usage, setUsage] = useState<Usage>();
  const [preset, setPreset] = useState<PresetId>("coding");
  const [raw, setRaw] = useState(
    typeof location.state?.content === "string" ? location.state.content : "",
  );
  const [tone, setTone] = useState<PromptTone>("professional");
  const [mode, setMode] = useState<CompileMode>("Build");
  const [engine, setEngine] = useState<GenerationEngine>("local");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [result, setResult] = useState<GenerationResponse>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [loaded, setLoaded] = useState(false);
  async function load() {
    setError("");
    try {
      const [a, b, c] = await Promise.all([
        api<PresetList>("/api/presets"),
        api<Capabilities>("/api/auth/capabilities"),
        api<Usage>("/api/usage"),
      ]);
      setCatalog(a);
      setCaps(b);
      setUsage(c);
      try {
        const d = await api<{ presets: Preset[] }>("/api/custom-presets");
        setCustom(d.presets);
      } catch (e) {
        if (!(e instanceof APIException && e.code === "pro_required")) throw e;
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoaded(true);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  const selected = [...(catalog?.presets || []), ...custom].find(
    (p) => p.id === preset,
  );
  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    setResult(undefined);
    setSaveOpen(false);
    try {
      const output = await post<GenerationResponse>(
        `/api/${engine === "ai" ? "refine" : "compile"}`,
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
      setUsage(await api<Usage>("/api/usage"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    if (!result) return;
    try {
      await copyText(result.prompt);
      setMessage("Prompt copied to clipboard.");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!result) return;
    setSaving(true);
    setError("");
    try {
      await post("/api/prompts", {
        title,
        content: result.prompt,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      setMessage("Prompt saved to your library.");
      setSaveOpen(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }
  if (!loaded) return <Busy />;
  return (
    <>
      <div className="heading-row">
        <Heading
          eyebrow="THE PROMPT WORKSPACE"
          title="A little clarity goes a long way."
          description="Shape your idea into instructions your assistant can work with."
        />
        {usage && (
          <div className="quota-chip">
            <Sparkles size={15} />
            <strong>
              {usage.remaining} / {usage.daily_ai_limit}
            </strong>
            <span>AI requests left today</span>
          </div>
        )}
      </div>
      <Notice error={error} message={message} />
      {!catalog ? (
        <Button onClick={() => void load()}>Retry loading presets</Button>
      ) : (
        <div className="editor-grid">
          <section className="panel editor-input">
            <div className="panel-header">
              <div>
                <span className="step-number">01</span>
                <h2>Your starting point</h2>
              </div>
              <span className="muted">INPUT</span>
            </div>
            <form onSubmit={(e) => void generate(e)}>
              <div className="editor-body">
                <label htmlFor="preset">Choose your preset</label>
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
                    <optgroup label="Your custom presets">
                      {custom.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                <p className="field-help">{selected?.role}</p>
                <label htmlFor="raw-input">
                  What do you want to accomplish?
                </label>
                <Textarea
                  id="raw-input"
                  required
                  maxLength={20000}
                  value={raw}
                  disabled={busy}
                  onChange={(e) => setRaw(e.target.value)}
                  placeholder="Describe the task, who it is for, and what a good result looks like…"
                  className="raw-input min-h-[195px]"
                />
                <div className="character-count">
                  {raw.length.toLocaleString()} / 20,000 characters
                </div>
                <div className="field-row">
                  <div>
                    <label htmlFor="tone">Tone</label>
                    <select
                      id="tone"
                      value={tone}
                      disabled={busy}
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
                      value={mode}
                      disabled={busy}
                      onChange={(e) => setMode(e.target.value as CompileMode)}
                    >
                      {catalog.modes.map((m) => (
                        <option key={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <p className="field-help">
                  {mode === "Build"
                    ? "Build adds structure and acceptance criteria."
                    : "Compact removes redundancy while preserving your intent."}
                </p>
                <button
                  type="button"
                  className="disclosure"
                  aria-expanded={advanced}
                  aria-controls="preset-fields"
                  onClick={() => setAdvanced(!advanced)}
                >
                  Add context & constraints{" "}
                  <ChevronDown
                    size={16}
                    className={advanced ? "rotate-180" : ""}
                  />
                </button>
                {advanced && (
                  <div id="preset-fields" className="advanced-fields">
                    {Object.entries({
                      ...selected?.required_fields,
                      ...selected?.optional_fields,
                    }).map(([key, description]) => (
                      <div key={key}>
                        <label htmlFor={"field-" + key}>
                          {key.replaceAll("_", " ")}{" "}
                          <small>
                            {key in (selected?.required_fields || {})
                              ? "Core context"
                              : "Optional"}
                          </small>
                        </label>
                        <Input
                          id={"field-" + key}
                          maxLength={4000}
                          disabled={busy}
                          value={fields[key] || ""}
                          onChange={(e) =>
                            setFields({ ...fields, [key]: e.target.value })
                          }
                          placeholder={description}
                        />
                      </div>
                    ))}
                  </div>
                )}
                <label htmlFor="engine">Generation method</label>
                <select
                  id="engine"
                  value={engine}
                  disabled={busy}
                  onChange={(e) =>
                    setEngine(e.target.value as GenerationEngine)
                  }
                >
                  <option value="local">
                    Local compiler · no AI quota used
                  </option>
                  <option value="ai" disabled={!caps?.ai_enabled}>
                    AI refinement {caps?.ai_enabled ? "" : "· not configured"}
                  </option>
                </select>
              </div>
              <div className="editor-actions">
                <span>
                  <ShieldLabel />
                </span>
                <Button
                  type="submit"
                  disabled={
                    busy ||
                    !raw.trim() ||
                    (engine === "ai" && !usage?.remaining)
                  }
                >
                  {busy ? (
                    <LoaderCircle className="animate-spin" />
                  ) : (
                    <WandSparkles />
                  )}
                  {busy
                    ? "Crafting…"
                    : engine === "ai"
                      ? "Refine with AI"
                      : "Build prompt"}{" "}
                  {!busy && <ArrowUpRight />}
                </Button>
              </div>
            </form>
          </section>
          <section className="panel editor-output">
            <div className="panel-header">
              <div>
                <span className="step-number">02</span>
                <h2>Your crafted prompt</h2>
              </div>
              {result ? (
                <span className="pill">
                  <Check size={12} /> READY
                </span>
              ) : (
                <span className="muted">OUTPUT</span>
              )}
            </div>
            {busy ? (
              <Busy text="Giving your idea a clear direction…" />
            ) : result ? (
              <div className="result-body">
                <div className="metric-grid">
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
                  <div
                    className={
                      result.metrics.is_reduction ? "metric-positive" : ""
                    }
                  >
                    <span>
                      {result.metrics.is_reduction
                        ? "Tokens reduced"
                        : "Tokens added"}
                    </span>
                    <strong>
                      {Math.abs(
                        result.metrics.token_difference,
                      ).toLocaleString()}
                      <small>
                        {Math.abs(result.metrics.reduction_percent).toFixed(1)}%
                      </small>
                    </strong>
                  </div>
                </div>
                <p className="metric-caption">
                  GPT-4o-mini text token counts. Other assistants tokenize
                  differently. Added detail can increase length.
                </p>
                <label className="sr-only" htmlFor="generated-prompt">
                  Generated prompt
                </label>
                <Textarea
                  id="generated-prompt"
                  readOnly
                  value={result.prompt}
                  className="generated-prompt min-h-[320px]"
                />
                {result.clarification_questions.length > 0 && (
                  <div className="clarifications">
                    <h3>Worth clarifying</h3>
                    <ul>
                      {result.clarification_questions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {result.assumptions.length > 0 && (
                  <details className="assumptions">
                    <summary>Assumptions ({result.assumptions.length})</summary>
                    <ul>
                      {result.assumptions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="result-actions">
                  <Button onClick={() => void copy()}>
                    <Copy />
                    Copy prompt
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setSaveOpen(!saveOpen)}
                  >
                    <Save />
                    Save to library
                  </Button>
                  <span className="muted">
                    {result.engine === "local"
                      ? "Local compiler"
                      : "AI refinement"}
                  </span>
                </div>
                {saveOpen && (
                  <form className="save-form" onSubmit={(e) => void save(e)}>
                    <label htmlFor="save-title">Prompt title</label>
                    <Input
                      id="save-title"
                      required
                      maxLength={200}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                    <label htmlFor="save-tags">
                      Tags <small>Comma separated, up to 20</small>
                    </label>
                    <Input
                      id="save-tags"
                      value={tags}
                      onChange={(e) => setTags(e.target.value)}
                      placeholder="client, proposal"
                    />
                    <Button disabled={saving} type="submit">
                      {saving ? "Saving…" : "Save prompt"}
                    </Button>
                  </form>
                )}
              </div>
            ) : (
              <div className="output-empty">
                <span className="output-symbol">
                  <Sparkles size={32} />
                </span>
                <h3>Give your idea a direction.</h3>
                <p>
                  Your structured prompt will appear here.
                  <br />
                  Ready to copy into your favorite assistant.
                </p>
                <div className="output-skeleton">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <div className="assistant-list">
                  ChatGPT <span>·</span> Claude <span>·</span> Gemini
                </div>
              </div>
            )}
          </section>
        </div>
      )}
      <div className="workspace-tip">
        <span className="pill">A SMALL TIP</span>
        <p>
          Add the audience, desired format, and constraints for a more useful
          prompt.
        </p>
        <span>Be specific. Stay intentional.</span>
      </div>
    </>
  );
}
function ShieldLabel() {
  return <>Saved only when you choose.</>;
}
