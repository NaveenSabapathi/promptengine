import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth";
import { api, post, csrfToken, errorText } from "@/lib/api";
import { Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
type Overview = {
  accounts: number;
  active_accounts: number;
  usage_today: number;
  telemetry: {
    requests: number;
    failures: number;
    failure_rate: number;
    provider_latency_ms: number | string | null;
  };
  tokens: { input_tokens: number; output_tokens: number; token_delta: number };
};
type Referral = {
  id: string;
  referrer_id: string;
  referee_id: string;
  status: string;
  blocked_reason: string | null;
  registration_days: number;
  conversion_days: number;
};
type Audit = {
  id: string;
  created_at: string;
  action: string;
  target: string;
  details: Record<string, unknown>;
};
type Account = {
  id: string;
  email: string;
  plan_tier: string;
  daily_ai_limit: number;
  devices: { id: string; name: string }[];
};
type Dataset = {
  id: string;
  preset_key: string;
  quality_rating: number | null;
  created_at: string;
};
export default function Admin() {
  const auth = useAuth();
  const [overview, setOverview] = useState<Overview>();
  const [users, setUsers] = useState<Account[]>([]);
  const [email, setEmail] = useState("");
  const [audit, setAudit] = useState<Audit[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [dataset, setDataset] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [days, setDays] = useState(7);
  const [limit, setLimit] = useState(100);
  const [tier, setTier] = useState("pro");
  const [kind, setKind] = useState("days_extension");
  const [uses, setUses] = useState(10);
  const [value, setValue] = useState(3);
  const [expiry, setExpiry] = useState(30);
  const [plan, setPlan] = useState("");
  const [recipient, setRecipient] = useState("");
  const [preview, setPreview] = useState<unknown>();
  const [coupon, setCoupon] = useState("");
  async function refresh() {
    const [o, u, a, r, d] = await Promise.all([
      api<Overview>("/api/admin/overview"),
      api<{ users: Account[] }>(
        "/api/admin/users?email=" + encodeURIComponent(email),
      ),
      api<{ logs: Audit[] }>("/api/admin/audit"),
      api<{ referrals: Referral[] }>("/api/admin/referrals"),
      api<{ logs: Dataset[] }>("/api/admin/dataset"),
    ]);
    setOverview(o);
    setUsers(u.users);
    setAudit(a.logs);
    setReferrals(r.referrals);
    setDataset(d.logs);
  }
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!auth.user?.is_admin) return;
    refresh().catch((e) => setError(errorText(e)));
    const timer = setInterval(() => {
      refresh().catch((e) => setError(errorText(e)));
    }, 30000);
    return () => clearInterval(timer);
  }, [auth.user?.is_admin]);
  if (!auth.user?.is_admin) return <p>Administrator access required.</p>;
  return (
    <>
      <h1>Administration</h1>
      <p>
        Server authorization and a recent authenticator verification are
        required. <Link to="/security">Verify sensitive actions</Link>
      </p>
      <Notice error={error} />
      <Button disabled={busy} onClick={() => void run(async () => {})}>
        Refresh dashboard
      </Button>
      <section className="card">
        <h2>Accounts, quota & provider telemetry</h2>
        {overview && (
          <div className="enterprise-metrics">
            {[
              ["Total accounts", overview.accounts],
              ["Active accounts", overview.active_accounts],
              ["AI requests today", overview.usage_today],
              [
                "API failure rate",
                (overview.telemetry.failure_rate * 100).toFixed(2) + "%",
              ],
              [
                "Provider latency",
                Number(overview.telemetry.provider_latency_ms || 0).toFixed(0) +
                  " ms",
              ],
              ["Provider input tokens", overview.tokens.input_tokens],
              ["Provider output tokens", overview.tokens.output_tokens],
              ["Prompt token delta", overview.tokens.token_delta],
            ].map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        )}
        <p>
          Active accounts have a non-revoked web session. Failure rates and
          token deltas cover the last 24 hours.
        </p>
      </section>
      <section className="card">
        <h2>Account lookup</h2>
        <label htmlFor="admin-email">Exact email</label>
        <Input
          id="admin-email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Button disabled={busy} onClick={() => void run(async () => {})}>
          Look up accounts
        </Button>
        <label htmlFor="admin-reason">Reason for sensitive action</label>
        <Input
          id="admin-reason"
          minLength={5}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <label htmlFor="override-tier">Override plan</label>
        <select
          id="override-tier"
          value={tier}
          onChange={(e) => setTier(e.target.value)}
        >
          <option>pro</option>
          <option>free</option>
        </select>
        <label htmlFor="override-limit">Daily AI quota</label>
        <Input
          id="override-limit"
          type="number"
          min={1}
          max={10000}
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
        />
        <label htmlFor="override-days">Override days</label>
        <Input
          id="override-days"
          type="number"
          min={1}
          max={365}
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        />
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Plan / quota</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>
                  {u.plan_tier} / {u.daily_ai_limit}
                </td>
                <td>
                  <Button
                    disabled={busy || reason.length < 5}
                    onClick={() =>
                      void run(async () => {
                        await post(`/api/admin/users/${u.id}/override`, {
                          reason,
                          plan_tier: tier,
                          daily_ai_limit: limit,
                          days,
                        });
                      })
                    }
                  >
                    Apply override
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy || reason.length < 5}
                    onClick={() =>
                      void run(async () => {
                        await post(`/api/admin/users/${u.id}/revoke`, {
                          reason,
                        });
                      })
                    }
                  >
                    Revoke all sessions
                  </Button>
                  {u.devices.map((d) => (
                    <Button
                      key={d.id}
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await api(`/api/admin/devices/${d.id}`, {
                            method: "DELETE",
                          });
                        })
                      }
                    >
                      Revoke {d.name}
                    </Button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h2>Generate secure coupon</h2>
        <label htmlFor="coupon-type">Discount type</label>
        <select
          id="coupon-type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="days_extension">Access days</option>
          <option value="percentage">Percentage</option>
          <option value="fixed_amount">Fixed amount in paise</option>
        </select>
        <label htmlFor="coupon-value">Days / percentage / paise</label>
        <Input
          id="coupon-value"
          type="number"
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
        />
        <label htmlFor="coupon-uses">Maximum redemptions</label>
        <Input
          id="coupon-uses"
          type="number"
          min={1}
          value={uses}
          onChange={(e) => setUses(Number(e.target.value))}
        />
        <label htmlFor="coupon-expiry">Expires in days</label>
        <Input
          id="coupon-expiry"
          type="number"
          min={1}
          max={365}
          value={expiry}
          onChange={(e) => setExpiry(Number(e.target.value))}
        />
        {kind !== "days_extension" && (
          <>
            <label htmlFor="coupon-plan">
              Verified discounted monthly Razorpay plan ID
            </label>
            <Input
              id="coupon-plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            />
          </>
        )}
        <label htmlFor="coupon-recipient">
          Optional email dispatch recipient
        </label>
        <Input
          id="coupon-recipient"
          type="email"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
        <Button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const r = await post<{ code: string }>("/api/admin/coupons", {
                discount_type: kind,
                max_uses: uses,
                expires_in_days: expiry,
                ...(kind === "days_extension"
                  ? { days_granted: value }
                  : { discount_value: value, razorpay_plan_id: plan }),
                ...(recipient ? { recipient_email: recipient } : {}),
              });
              setCoupon(r.code);
            })
          }
        >
          Generate coupon
        </Button>
        {coupon && (
          <p role="status">
            Coupon: <strong>{coupon}</strong>
          </p>
        )}
      </section>
      <section className="card">
        <h2>Referral ledger</h2>
        <table>
          <thead>
            <tr>
              <th>Referrer</th>
              <th>Referee</th>
              <th>Status</th>
              <th>Days granted</th>
              <th>Risk review</th>
            </tr>
          </thead>
          <tbody>
            {referrals.map((r) => (
              <tr key={r.id}>
                <td>{r.referrer_id}</td>
                <td>{r.referee_id}</td>
                <td>{r.status}</td>
                <td>{r.registration_days + r.conversion_days}</td>
                <td>{r.blocked_reason || "Passed checks"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h2>Dataset quality & export</h2>
        <p>
          Exports include consenting users’ records rated at least 3/5 and
          retained within 30 days.
        </p>
        <Button
          disabled={busy || reason.length < 5}
          onClick={() =>
            void run(async () => {
              const response = await fetch("/api/admin/dataset/export", {
                method: "POST",
                credentials: "include",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRF-TOKEN": decodeURIComponent(csrfToken() || ""),
                },
                body: JSON.stringify({ reason, minimum_rating: 3 }),
              });
              if (!response.ok)
                throw new Error(
                  "Export denied; check your MFA verification and reason.",
                );
              const url = URL.createObjectURL(await response.blob());
              const a = document.createElement("a");
              a.href = url;
              a.download = "promptlogic-training.ndjson";
              a.click();
              URL.revokeObjectURL(url);
            })
          }
        >
          Download NDJSON
        </Button>
        {preview !== undefined && <pre>{JSON.stringify(preview, null, 2)}</pre>}
        <table>
          <thead>
            <tr>
              <th>Preset</th>
              <th>Created</th>
              <th>Quality</th>
            </tr>
          </thead>
          <tbody>
            {dataset.map((d) => (
              <tr key={d.id}>
                <td>
                  {d.preset_key}
                  <Button
                    disabled={busy}
                    variant="outline"
                    onClick={() =>
                      void run(async () => {
                        setPreview(await api(`/api/admin/dataset/${d.id}`));
                      })
                    }
                  >
                    Review scrubbed content
                  </Button>
                </td>
                <td>{d.created_at}</td>
                <td>
                  <select
                    aria-label={`Quality rating ${d.id}`}
                    value={d.quality_rating || ""}
                    disabled={busy}
                    onChange={(e) =>
                      void run(async () => {
                        await api(`/api/admin/dataset/${d.id}/rating`, {
                          method: "PUT",
                          body: JSON.stringify({
                            quality_rating: Number(e.target.value),
                          }),
                        });
                      })
                    }
                  >
                    <option value="" disabled>
                      Unrated
                    </option>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h2>Audit trail</h2>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>Target</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.action}</td>
                <td>{r.target}</td>
                <td>{JSON.stringify(r.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
