import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, RefreshCw, Sparkles, Puzzle } from "lucide-react";
import type {
  BillingStatus,
  BillingPlanList,
  BillingSubscription,
  Usage,
  MetricsSummary,
  OAuthProvider,
} from "@promptengine/shared-types";
import { useAuth } from "@/auth";
import { api, post, errorText } from "@/lib/api";
import { money, date, safeCheckout } from "@/lib/utils";
import { Heading, Busy, Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import type { Capabilities } from "./Login";
export default function SettingsPage() {
  const auth = useAuth();
  const [status, setStatus] = useState<BillingStatus>();
  const [plans, setPlans] = useState<BillingPlanList>();
  const [usage, setUsage] = useState<Usage>();
  const [metrics, setMetrics] = useState<MetricsSummary>();
  const [caps, setCaps] = useState<Capabilities>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function load() {
    try {
      const [s, p, u, m, c] = await Promise.all([
        api<BillingStatus>("/api/billing/status"),
        api<BillingPlanList>("/api/billing/plans"),
        api<Usage>("/api/usage"),
        api<MetricsSummary>("/api/generation-metrics?days=30"),
        api<Capabilities>("/api/auth/capabilities"),
      ]);
      setStatus(s);
      setPlans(p);
      setUsage(u);
      setMetrics(m);
      setCaps(c);
    } catch (e) {
      setError(errorText(e));
    }
  }
  useEffect(() => {
    void load();
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);
  async function subscribe() {
    setBusy(true);
    setError("");
    try {
      const response = await post<{ subscription: BillingSubscription }>(
        "/api/billing/subscribe",
        { plan_tier: "pro" },
      );
      if (!response.subscription.checkout_url)
        throw new Error(
          "Checkout is unavailable. Refresh your subscription status.",
        );
      window.location.assign(safeCheckout(response.subscription.checkout_url));
    } catch (e) {
      setError(errorText(e));
      await load();
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    setBusy(true);
    setError("");
    try {
      await post("/api/billing/cancel", { at_cycle_end: true });
      setConfirm(false);
      setMessage(
        "Cancellation confirmed. Refresh the status below for your remaining access.",
      );
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function link(provider: OAuthProvider) {
    setBusy(true);
    setError("");
    try {
      const result = await post<{ authorization_url: string }>(
        `/api/auth/${provider}/link`,
        {},
      );
      const url = new URL(result.authorization_url);
      if (
        url.protocol !== "https:" ||
        !["accounts.google.com", "login.microsoftonline.com"].includes(
          url.hostname,
        )
      )
        throw new Error("Provider returned an invalid login address");
      window.location.assign(url.href);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const summary = metrics?.groups.reduce(
    (a, g) => ({
      count: a.count + g.generations,
      difference: a.difference + g.token_difference,
    }),
    { count: 0, difference: 0 },
  );
  const sub = status?.subscription;
  const pro = plans?.plans.find((p) => p.tier === "pro");
  const blocked =
    sub &&
    ["creating", "uncertain", "active", "pending", "halted"].includes(
      sub.status,
    );
  const mayCancel =
    sub &&
    ["active", "pending", "halted", "authenticated", "created"].includes(
      sub.status,
    ) &&
    !sub.cancel_at_cycle_end;
  return (
    <>
      <div className="heading-row">
        <Heading
          eyebrow="ACCOUNT & BILLING"
          title="Your workspace, your way."
          description="Manage your account, daily quota, and subscription."
        />
        <Button variant="outline" disabled={busy} onClick={() => void load()}>
          <RefreshCw />
          Refresh status
        </Button>
      </div>
      <Notice error={error} message={message} />
      {!status || !plans || !usage ? (
        <>{!error && <Busy text="Loading account details…" />}</>
      ) : (
        <>
          <div className="settings-metrics">
            <div className="panel metric-card">
              <span className="eyebrow">CURRENT PLAN</span>
              <strong>{status.plan_tier === "pro" ? "Pro" : "Free"}</strong>
              <span>
                {status.billing_enabled
                  ? "Monthly workspace plan"
                  : "Free beta · paid checkout disabled"}
              </span>
            </div>
            <div className="panel metric-card">
              <span className="eyebrow">AI USAGE TODAY</span>
              <strong>
                {usage.used}
                <small> / {usage.daily_ai_limit}</small>
              </strong>
              <progress
                max={usage.daily_ai_limit}
                value={Math.min(usage.used, usage.daily_ai_limit)}
                aria-label="Daily AI usage"
              />
              <span>Resets at 00:00 UTC · {usage.remaining} remaining</span>
            </div>
            <div className="panel metric-card">
              <span className="eyebrow">LAST 30 DAYS</span>
              <strong>
                {summary?.count || 0}
                <small> generations</small>
              </strong>
              <span>
                {Math.abs(summary?.difference || 0).toLocaleString()} net text
                tokens {(summary?.difference || 0) >= 0 ? "reduced" : "added"}
              </span>
            </div>
          </div>
          <div className="settings-grid">
            <section className="panel settings-card">
              <span className="eyebrow">YOUR ACCOUNT</span>
              <h2>Account details</h2>
              <div className="account-data">
                <span>Email address</span>
                <strong>{auth.user?.email}</strong>
                <span>Member since</span>
                <strong>{auth.user && date(auth.user.created_at)}</strong>
              </div>
              <h3>Connected sign-in methods</h3>
              <p>
                Link providers while signed in to keep your existing account and
                saved prompts.
              </p>
              {(["google", "microsoft"] as const).map((p) => (
                <div key={p} className="connected-provider">
                  <span>{p === "google" ? "Google" : "Microsoft"}</span>
                  {auth.linked.includes(p) ? (
                    <span className="pill">
                      <Check size={12} /> CONNECTED
                    </span>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy || !caps?.providers[p]}
                      onClick={() => void link(p)}
                    >
                      {caps?.providers[p] ? "Connect" : "Not configured"}
                    </Button>
                  )}
                </div>
              ))}
              <div className="settings-extension">
                <Puzzle size={18} />
                <Link to="/settings/extensions">
                  Manage connected browsers <ArrowUpRight size={14} />
                </Link>
              </div>
            </section>
            <section className="panel settings-card billing-card">
              <span className="eyebrow">ROOM TO DO MORE</span>
              <h2>
                PromptEngine Pro <Sparkles size={22} />
              </h2>
              <div className="pro-price">
                {pro && money(pro.amount_paise)}
                <span>/ month</span>
              </div>
              {!status.billing_enabled && (
                <span className="pill">
                  PLANNED PRICING · CHECKOUT DISABLED
                </span>
              )}
              <ul>
                <li>
                  <Check size={17} />
                  {pro?.daily_ai_limit} AI requests per day when configured
                </li>
                <li>
                  <Check size={17} />
                  Create your own custom presets
                </li>
                <li>
                  <Check size={17} />
                  Local compilation & your private prompt library
                </li>
              </ul>
              {status.billing_enabled ? (
                <Button
                  disabled={
                    busy || Boolean(blocked) || status.plan_tier === "pro"
                  }
                  onClick={() => void subscribe()}
                >
                  {busy
                    ? "Please wait…"
                    : status.plan_tier === "pro"
                      ? "You are on Pro"
                      : blocked
                        ? "Subscription needs attention"
                        : sub?.checkout_url &&
                            ["created", "authenticated"].includes(sub.status)
                          ? "Continue checkout"
                          : "Upgrade to Pro"}
                  <ArrowUpRight />
                </Button>
              ) : (
                <div className="beta-callout">
                  You’re in the free beta. Custom presets are included while
                  billing is disabled.
                </div>
              )}
              <p className="field-help">
                Pro access is enabled only after a verified payment webhook.
                Returning from checkout does not confirm payment.
              </p>
            </section>
          </div>
          {sub && (
            <section className="panel settings-card subscription-card">
              <div className="heading-row">
                <div>
                  <span className="eyebrow">SUBSCRIPTION STATUS</span>
                  <h2>{sub.status.replaceAll("_", " ")}</h2>
                </div>
                <span className="pill">
                  {sub.currency} {money(sub.amount_paise)}
                </span>
              </div>
              <p>Reference: {sub.razorpay_subscription_id || sub.id}</p>
              {sub.current_end && (
                <p>Current period ends {date(sub.current_end)}.</p>
              )}
              {sub.cancel_at_cycle_end && (
                <Notice message="Cancellation is scheduled for the end of the current billing period." />
              )}
              {["creating", "uncertain"].includes(sub.status) && (
                <Notice error="Checkout needs reconciliation. Contact your administrator with the reference above before retrying payment." />
              )}
              {mayCancel && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setConfirm(true)}
                >
                  Cancel subscription
                </Button>
              )}
              {confirm && (
                <div
                  className="confirmation"
                  role="alertdialog"
                  aria-labelledby="cancel-title"
                >
                  <h3 id="cancel-title">
                    Cancel at the end of this billing period?
                  </h3>
                  <p>
                    You will retain access through the paid period once
                    cancellation is confirmed.
                  </p>
                  <div className="button-row">
                    <Button
                      variant="destructive"
                      disabled={busy}
                      onClick={() => void cancel()}
                    >
                      Confirm cancellation
                    </Button>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => setConfirm(false)}
                    >
                      Keep subscription
                    </Button>
                  </div>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}
