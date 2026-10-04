import { useEffect, useState, type FormEvent } from "react";
import { Puzzle, Check, Trash2 } from "lucide-react";
import type { ExtensionDevice } from "@promptengine/shared-types";
import { api, post, errorText } from "@/lib/api";
import { date } from "@/lib/utils";
import { Heading, Notice, Empty } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
interface PairingInspection {
  device_name: string;
  scopes: string[];
  expires_at: string;
  approved: boolean;
}
export default function Extensions() {
  const [code, setCode] = useState("");
  const [inspection, setInspection] = useState<PairingInspection>();
  const [devices, setDevices] = useState<ExtensionDevice[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [revoke, setRevoke] = useState<ExtensionDevice>();
  async function load() {
    try {
      setDevices(
        (await api<{ tokens: ExtensionDevice[] }>("/api/extension/tokens"))
          .tokens,
      );
    } catch (e) {
      setError(errorText(e));
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function inspect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setInspection(undefined);
    try {
      setInspection(
        await post<PairingInspection>("/api/extension/pairing/inspect", {
          code,
        }),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function approve() {
    setBusy(true);
    setError("");
    try {
      await post("/api/extension/pairing/approve", { code });
      setInspection(undefined);
      setCode("");
      setMessage(
        "Browser approved. Return to the extension to complete pairing.",
      );
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function revokeDevice() {
    if (!revoke) return;
    setBusy(true);
    try {
      await api(`/api/extension/tokens/${revoke.id}`, { method: "DELETE" });
      setRevoke(undefined);
      setMessage("Browser access revoked.");
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="CONNECTED BROWSERS"
        title="Your workspace, within reach."
        description="Approve a pairing code from your extension and manage its access."
      />
      <Notice error={error} message={message} />
      <section className="panel settings-card">
        <Puzzle size={24} />
        <h2>Pair your extension</h2>
        <p>
          Enter the six-digit code shown in your extension. Codes expire after
          five minutes. Approve only a browser you recognize.
        </p>
        <form className="pairing-form" onSubmit={(e) => void inspect(e)}>
          <label htmlFor="pairing-code">Pairing code</label>
          <div className="button-row">
            <Input
              id="pairing-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              required
              value={code}
              onChange={(e) => {
                setCode(e.target.value.replace(/\D/g, ""));
                setInspection(undefined);
              }}
              placeholder="000000"
            />
            <Button type="submit" disabled={busy || code.length !== 6}>
              Review browser
            </Button>
          </div>
        </form>
        {inspection && (
          <div className="pairing-review">
            <h3>{inspection.device_name}</h3>
            <p>Requested access: {inspection.scopes.join(", ")}</p>
            <p>
              Expires {new Date(inspection.expires_at).toLocaleTimeString()}
            </p>
            <Button
              disabled={busy || inspection.approved}
              onClick={() => void approve()}
            >
              <Check />
              {inspection.approved
                ? "Already approved"
                : "Approve this browser"}
            </Button>
          </div>
        )}
      </section>
      <section className="panel settings-card">
        <h2>Connected devices</h2>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          Refresh devices
        </Button>
        {devices.length ? (
          devices.map((d) => (
            <div className="connected-provider" key={d.id}>
              <div>
                <strong>{d.device_name}</strong>
                <p>
                  Expires {date(d.expires_at)} ·{" "}
                  {d.revoked
                    ? "Revoked"
                    : new Date(d.expires_at) < new Date()
                      ? "Expired"
                      : "Active"}
                </p>
              </div>
              <Button
                variant="outline"
                disabled={busy || d.revoked}
                onClick={() => setRevoke(d)}
              >
                <Trash2 />
                Revoke
              </Button>
            </div>
          ))
        ) : (
          <Empty
            title="No browsers connected"
            text="Paired browsers will appear here after the extension exchanges its approved code."
          />
        )}
        {revoke && (
          <div
            className="confirmation"
            role="alertdialog"
            aria-labelledby="revoke-title"
          >
            <h3 id="revoke-title">Revoke access for {revoke.device_name}?</h3>
            <div className="button-row">
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => void revokeDevice()}
              >
                Revoke browser
              </Button>
              <Button variant="outline" onClick={() => setRevoke(undefined)}>
                Keep access
              </Button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
