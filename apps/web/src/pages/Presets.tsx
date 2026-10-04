import { useEffect, useState, type FormEvent } from "react";
import { Plus, Pencil, Trash2, Puzzle } from "lucide-react";
import type { Preset, CustomPresetInput } from "@promptengine/shared-types";
import { api, APIException, errorText } from "@/lib/api";
import { Heading, Notice, Empty, Busy } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Link } from "react-router-dom";
function parseFields(text: string) {
  const fields: Record<string, string> = {};
  for (const line of text.split("\n").filter((l) => l.trim())) {
    const index = line.indexOf("|");
    const key = line.slice(0, index).trim();
    const description = line.slice(index + 1).trim();
    if (
      index < 1 ||
      !description ||
      !/^[a-z][a-z0-9_]{0,39}$/.test(key) ||
      Object.hasOwn(fields, key)
    )
      throw new Error(
        "Use a unique lowercase field key and description on each line: audience | Who is this for?",
      );
    fields[key] = description;
  }
  return fields;
}
export default function Presets() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [required, setRequired] = useState(
    "objective | What should this task accomplish?",
  );
  const [optional, setOptional] = useState("");
  const [constraints, setConstraints] = useState(
    "Return clear, actionable instructions.",
  );
  const [busy, setBusy] = useState(false);
  const [remove, setRemove] = useState<Preset>();
  async function load() {
    try {
      setPresets(
        (await api<{ presets: Preset[] }>("/api/custom-presets")).presets,
      );
      setLocked(false);
    } catch (e) {
      if (e instanceof APIException && e.code === "pro_required")
        setLocked(true);
      else setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function edit(p?: Preset) {
    setId(p?.id.slice(7) || "");
    setName(p?.name || "");
    setRole(p?.role || "");
    setRequired(
      p
        ? Object.entries(p.required_fields)
            .map(([k, v]) => `${k} | ${v}`)
            .join("\n")
        : "objective | What should this task accomplish?",
    );
    setOptional(
      p
        ? Object.entries(p.optional_fields)
            .map(([k, v]) => `${k} | ${v}`)
            .join("\n")
        : "",
    );
    setConstraints(
      p?.output_constraints.join("\n") ||
        "Return clear, actionable instructions.",
    );
    setOpen(true);
    setError("");
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data: CustomPresetInput = {
        name,
        role,
        required_fields: parseFields(required),
        optional_fields: parseFields(optional),
        output_constraints: constraints
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
      };
      await api(`/api/custom-presets${id ? "/" + id : ""}`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      });
      setOpen(false);
      setMessage("Preset saved. It is now available in your prompt editor.");
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function deletePreset() {
    if (!remove) return;
    setBusy(true);
    try {
      await api(`/api/custom-presets/${remove.id.slice(7)}`, {
        method: "DELETE",
      });
      setRemove(undefined);
      setMessage("Preset deleted.");
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="heading-row">
        <Heading
          eyebrow="YOUR OWN PLAYBOOK"
          title="Make good structure repeatable."
          description="Create private presets for the work you do again and again."
        />
        {!locked && (
          <Button onClick={() => edit()}>
            <Plus />
            New preset
          </Button>
        )}
      </div>
      <Notice error={error} message={message} />
      {loading ? (
        <Busy />
      ) : locked ? (
        <section className="panel settings-card">
          <Puzzle size={24} />
          <h2>Custom presets are a Pro feature</h2>
          <p>Your six core presets remain available in the workspace.</p>
          <Button asChild>
            <Link to="/settings">View plans</Link>
          </Button>
        </section>
      ) : presets.length ? (
        <div className="preset-grid">
          {presets.map((p) => (
            <article key={p.id} className="panel preset-card">
              <Puzzle size={22} />
              <h2>{p.name}</h2>
              <p>{p.role}</p>
              <span className="muted">
                {Object.keys(p.required_fields).length} core fields ·{" "}
                {p.output_constraints.length} constraints
              </span>
              <div className="button-row">
                <Button variant="outline" size="sm" onClick={() => edit(p)}>
                  <Pencil />
                  Edit
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setRemove(p)}>
                  <Trash2 />
                  Delete
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <section className="panel">
          <Empty
            title="A preset for your kind of work"
            text="Define a role, core context, and output rules. Your custom preset stays private to your account."
          />
        </section>
      )}
      {remove && (
        <div
          className="panel confirmation"
          role="alertdialog"
          aria-labelledby="remove-preset-title"
        >
          <h3 id="remove-preset-title">Delete {remove.name}?</h3>
          <div className="button-row">
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void deletePreset()}
            >
              Delete preset
            </Button>
            <Button variant="outline" onClick={() => setRemove(undefined)}>
              Keep preset
            </Button>
          </div>
        </div>
      )}
      {open && (
        <section className="panel detail-panel">
          <div className="panel-header">
            <h2>{id ? "Edit preset" : "Create a preset"}</h2>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Close
            </Button>
          </div>
          <form onSubmit={(e) => void save(e)}>
            <label htmlFor="preset-name">Preset name</label>
            <Input
              id="preset-name"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Client project brief"
            />
            <label htmlFor="preset-role">Assistant role</label>
            <Input
              id="preset-role"
              required
              maxLength={200}
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Act as a senior project manager."
            />
            <div className="field-row">
              <div>
                <label htmlFor="required-fields">Core fields</label>
                <Textarea
                  id="required-fields"
                  required
                  value={required}
                  onChange={(e) => setRequired(e.target.value)}
                  className="font-mono"
                />
                <p className="field-help">
                  One key | description per line. Include objective. Up to six
                  fields.
                </p>
              </div>
              <div>
                <label htmlFor="optional-fields">Optional fields</label>
                <Textarea
                  id="optional-fields"
                  value={optional}
                  onChange={(e) => setOptional(e.target.value)}
                  placeholder="audience | Who will read this?"
                  className="font-mono"
                />
                <p className="field-help">
                  Use unique lowercase keys, e.g. audience or output_format.
                </p>
              </div>
            </div>
            <label htmlFor="constraints">Output constraints</label>
            <Textarea
              id="constraints"
              required
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
            />
            <p className="field-help">
              One constraint per line. Between one and six, up to 500 characters
              each.
            </p>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save preset"}
            </Button>
          </form>
        </section>
      )}
    </>
  );
}
