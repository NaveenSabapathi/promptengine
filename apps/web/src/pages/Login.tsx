import { useEffect, useState, type FormEvent } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { ArrowRight, Check, LoaderCircle } from "lucide-react";
import type { AuthResponse } from "@promptengine/shared-types";
import { useAuth } from "@/auth";
import { api, post, errorText, APIException } from "@/lib/api";
import { Brand, Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
export interface Capabilities {
  providers: { google: boolean; microsoft: boolean };
  ai_enabled: boolean;
}
const oauthErrors: Record<string, string> = {
  account_link_required:
    "This email already has an account. Sign in with your existing method, then link the provider in Settings.",
  identity_in_use: "This provider is connected to another account.",
  provider_not_configured: "That login provider is not available yet.",
  provider_unavailable:
    "The login provider is temporarily unavailable. Try again later.",
  invalid_oauth_state: "Your sign-in attempt expired. Please start again.",
};
export default function Login({ signup = false }: { signup?: boolean }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [caps, setCaps] = useState<Capabilities>();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [mfa, setMfa] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [show, setShow] = useState(false);
  const from =
    typeof location.state?.from === "string" &&
    /^\/(workspace|history|presets|settings)(\/extensions)?$/.test(
      location.state.from,
    )
      ? location.state.from
      : "/workspace";
  useEffect(() => {
    api<Capabilities>("/api/auth/capabilities")
      .then(setCaps)
      .catch((e) => setError(errorText(e)));
  }, []);
  if (auth.user) return <Navigate to={from} replace />;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post<AuthResponse>(`/api/auth/${signup ? "signup" : "login"}`, {
        email,
        password,
        ...(code ? { code } : {}),
        ...(signup
          ? {
              device_id: deviceId(),
              ...(params.get("ref")
                ? { referral_code: params.get("ref") }
                : {}),
            }
          : {}),
      });
      await auth.refresh();
      navigate(from, { replace: true });
    } catch (e) {
      if (e instanceof APIException && e.code === "mfa_required") setMfa(true);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const oauthError = params.get("error");
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand />
        <div>
          <span className="eyebrow">A BETTER BEGINNING</span>
          <h1>
            Great work starts
            <br />
            with a clear ask.
          </h1>
          <p>Your ideas deserve more than a blank chat box.</p>
          <ul>
            {[
              "Six purpose-built prompt presets",
              "Precise token comparisons",
              "A private library for your best prompts",
            ].map((x) => (
              <li key={x}>
                <Check size={18} />
                {x}
              </li>
            ))}
          </ul>
        </div>
        <span className="auth-foot">Clarity before execution.</span>
      </section>
      <section className="auth-form-area">
        <Link className="back-link" to="/">
          ← Back to home
        </Link>
        <div className="auth-form">
          <span className="eyebrow">YOUR WORKSPACE AWAITS</span>
          <h1>{signup ? "Create your account" : "Welcome back"}</h1>
          <p>
            {signup
              ? "Bring a rough idea. Leave with a clear direction."
              : "Sign in to pick up where you left off."}
          </p>
          <Notice
            error={
              error ||
              (oauthError
                ? oauthErrors[oauthError] ||
                  "Provider sign-in could not be completed. Please try again."
                : "")
            }
          />
          <div className="provider-buttons">
            <Button
              variant="outline"
              disabled={busy || !caps?.providers.google}
              onClick={() => {
                window.location.assign("/api/auth/google/login");
              }}
            >
              <span className="google-mark" aria-hidden="true">
                G
              </span>
              Continue with Google
            </Button>
            <Button
              variant="outline"
              disabled={busy || !caps?.providers.microsoft}
              onClick={() => {
                window.location.assign("/api/auth/microsoft/login");
              }}
            >
              <span className="microsoft-mark" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
              </span>
              Continue with Microsoft
            </Button>
          </div>
          {caps && (!caps.providers.google || !caps.providers.microsoft) && (
            <small className="muted">
              Unavailable providers will be enabled once configured.
            </small>
          )}
          <div className="or-divider">
            <span />
            or continue with email
            <span />
          </div>
          <form onSubmit={(e) => void submit(e)}>
            <label htmlFor="email">Email address</label>
            <Input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
            <label htmlFor="password">
              Password <small>{signup ? "12–128 characters" : ""}</small>
            </label>
            <div className="password-field">
              <Input
                id="password"
                name="password"
                required
                minLength={signup ? 12 : 1}
                maxLength={128}
                type={show ? "text" : "password"}
                autoComplete={signup ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                aria-label={show ? "Hide password" : "Show password"}
                onClick={() => setShow(!show)}
              >
                {show ? "Hide" : "Show"}
              </button>
            </div>
            {mfa && (
              <>
                <label htmlFor="login-code">
                  Authenticator or recovery code
                </label>
                <Input
                  id="login-code"
                  autoComplete="one-time-code"
                  required
                  maxLength={80}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </>
            )}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <ArrowRight />
              )}
              {signup ? "Create account" : "Sign in"}
            </Button>
          </form>
          <p className="auth-switch">
            {signup ? "Already have an account?" : "New to PromptEngine?"}{" "}
            <Link to={signup ? "/login" : "/signup"} state={{ from }}>
              {signup ? "Sign in" : "Create an account"}
            </Link>
          </p>
          <p className="auth-privacy">
            Your login stays in a secure server-managed session.
          </p>
        </div>
      </section>
    </main>
  );
}

function deviceId() {
  let value = localStorage.getItem("referral-device-id");
  if (!value) {
    value = crypto.randomUUID();
    localStorage.setItem("referral-device-id", value);
  }
  return value;
}
