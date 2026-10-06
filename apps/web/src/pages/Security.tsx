import { useEffect, useState } from "react";
import { api, post, errorText } from "@/lib/api";
import { Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/auth";
export default function Security() {
  const auth = useAuth();
  const [status, setStatus] = useState<{
    enabled: boolean;
    recovery_codes_remaining: number;
    dataset_consent: boolean;
  }>();
  const [password, setPassword] = useState("");
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () => api<typeof status>("/api/security").then(setStatus);
  useEffect(() => {
    refresh().catch((e) => setError(errorText(e)));
  }, []);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      await refresh();
      await auth.refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
      setCode("");
    }
  }
  return (
    <>
      <h1>Security & privacy</h1>
      <Notice error={error} />
      <p role="status">{message}</p>
      {!status?.enabled && (
        <>
          <label htmlFor="enroll-password">
            Current password (email accounts)
          </label>
          <Input
            id="enroll-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </>
      )}
      <section className="card">
        <h2>Two-factor authentication</h2>
        <p>
          {status?.enabled
            ? `Enabled · ${status.recovery_codes_remaining} recovery codes left`
            : "Protect your account with an authenticator app."}
        </p>
        {!status?.enabled && (
          <Button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const result = await post<{ qr_data_url: string }>(
                  "/api/security/enroll",
                  { password },
                );
                setQr(result.qr_data_url);
              })
            }
          >
            Set up authenticator
          </Button>
        )}
        {qr && !status?.enabled && (
          <div>
            <img
              src={qr}
              alt="Scan this private authenticator QR code"
              width={220}
            />
            <p>Scan with your authenticator, then enter its six-digit code.</p>
          </div>
        )}
        {(qr || status?.enabled) && (
          <>
            <label htmlFor="mfa-code">Authenticator or recovery code</label>
            <Input
              id="mfa-code"
              value={code}
              maxLength={80}
              autoComplete="one-time-code"
              onChange={(e) => setCode(e.target.value)}
            />
            {!status?.enabled ? (
              <Button
                disabled={busy || !code}
                onClick={() =>
                  void run(async () => {
                    const r = await post<{ recovery_codes: string[] }>(
                      "/api/security/confirm",
                      { code },
                    );
                    setCodes(r.recovery_codes);
                    setQr("");
                  })
                }
              >
                Confirm setup
              </Button>
            ) : (
              <>
                <Button
                  disabled={busy || !code}
                  onClick={() =>
                    void run(async () => {
                      await post("/api/security/step-up", { code });
                      setMessage(
                        "Verified. Administrative actions are available for five minutes.",
                      );
                    })
                  }
                >
                  Verify sensitive actions
                </Button>
                <Button
                  variant="outline"
                  disabled={busy || !code || auth.user?.is_admin}
                  onClick={() =>
                    void run(async () => {
                      await post("/api/security/disable", { code });
                    })
                  }
                >
                  Disable two-factor authentication
                </Button>
              </>
            )}
          </>
        )}
        {codes.length > 0 && (
          <div role="status">
            <h3>Save these eight recovery codes now</h3>
            <p>Each works once. They will not be displayed again.</p>
            <pre>{codes.join("\n")}</pre>
            <Button onClick={() => setCodes([])}>I have saved my codes</Button>
          </div>
        )}
      </section>
      <section className="card">
        <h2>Optional training data</h2>
        <p>
          Off by default. Opting in allows scrubbed personal AI tasks and
          generated prompts to be retained for 30 days and exported by
          administrators for model training. Automated scrubbing cannot identify
          every sensitive detail. Team content is excluded. Turning this off
          deletes queued and stored records; it cannot undo an earlier export or
          training run.
        </p>
        <Button
          disabled={busy || !status}
          variant="outline"
          onClick={() =>
            void run(async () => {
              await post("/api/dataset/consent", {
                enabled: !status?.dataset_consent,
              });
            })
          }
        >
          {status?.dataset_consent
            ? "Revoke consent and delete records"
            : "Opt in to training data"}
        </Button>
      </section>
    </>
  );
}
