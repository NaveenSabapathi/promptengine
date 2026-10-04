import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  Layers,
  ScanText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { BillingPlanList } from "@promptengine/shared-types";
import { api, errorText } from "@/lib/api";
import { money } from "@/lib/utils";
import { Brand, Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
export default function Landing() {
  const [plans, setPlans] = useState<BillingPlanList>();
  const [error, setError] = useState("");
  useEffect(() => {
    api<BillingPlanList>("/api/billing/plans")
      .then(setPlans)
      .catch((e) => setError(errorText(e)));
  }, []);
  return (
    <div className="landing">
      <header className="public-nav">
        <Brand />
        <nav aria-label="Main navigation">
          <a href="#features">Features</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login">Sign in</Link>
          <Button asChild size="sm">
            <Link to="/signup">
              Get started <ArrowRight />
            </Link>
          </Button>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <span className="pill">
              <span className="status-dot" /> LESS GUESSWORK. BETTER PROMPTS.
            </span>
            <h1>
              Your rough idea.
              <br />A sharper <em>starting point.</em>
            </h1>
            <p>
              Give your AI the direction it deserves. Turn a raw command into a
              clear, structured prompt for ChatGPT, Claude, or Gemini.
            </p>
            <div className="hero-actions">
              <Button asChild size="lg">
                <Link to="/signup">
                  Build your first prompt <ArrowRight />
                </Link>
              </Button>
              <a href="#features">
                See how it works <ArrowRight size={16} />
              </a>
            </div>
            <div className="hero-proof">
              <ShieldCheck size={16} /> Local compilation included{" "}
              <span>·</span> Save only what you choose
            </div>
          </div>
          <div className="hero-demo">
            <div className="demo-top">
              <span className="window-dots">● ● ●</span>
              <span>promptengine / workspace</span>
              <span className="pill">EXAMPLE</span>
            </div>
            <div className="demo-input">
              <span className="eyebrow">01 / YOUR IDEA</span>
              <p>Build a client dashboard for our consulting team.</p>
              <span className="demo-tag">Website briefs</span>
              <span className="demo-tag">Professional</span>
            </div>
            <div className="demo-divider">
              <Sparkles size={16} />
              <span>A little structure goes a long way</span>
            </div>
            <div className="demo-output">
              <span className="eyebrow">02 / A CLEAR DIRECTION</span>
              <p>
                <b>Role</b> · Act as a senior product designer.
              </p>
              <p>
                <b>Task</b> · Design a client dashboard for a consulting team.
              </p>
              <p>
                <b>Clarify</b> · Who uses it? Which project updates matter?
              </p>
              <p>
                <b>Deliver</b> · A page plan, key workflows, and acceptance
                criteria.
              </p>
              <span className="demo-ready">
                <Check size={14} /> Ready to make your own
              </span>
            </div>
          </div>
        </section>
        <div className="compatibility">
          ONE WORKSPACE. YOUR CHOICE OF ASSISTANT.
          <div>
            <span>ChatGPT</span>
            <span>Claude</span>
            <span>Gemini</span>
          </div>
          <small>
            Copy your prompt into any assistant. No affiliation implied.
          </small>
        </div>
        <section id="features" className="features">
          <div className="section-heading">
            <span className="eyebrow">FROM INTENT TO INSTRUCTION</span>
            <h2>
              Better direction.
              <br />
              Less back and forth.
            </h2>
            <p>A focused workspace for the moment before you ask AI.</p>
          </div>
          <div className="feature-grid">
            {[
              [
                Layers,
                "Start with a proven structure",
                "Six presets for coding, websites, proposals, marketing, research, and professional communication.",
              ],
              [
                ScanText,
                "See the actual token change",
                "Compare input and output tokens, including when structure adds detail instead of reducing length.",
              ],
              [
                ShieldCheck,
                "Choose what gets saved",
                "Keep generations temporary, or save selected prompts to your private, searchable library.",
              ],
            ].map(([Icon, title, text]) => {
              const C = Icon as typeof Layers;
              return (
                <article key={String(title)}>
                  <C size={24} />
                  <h3>{String(title)}</h3>
                  <p>{String(text)}</p>
                </article>
              );
            })}
          </div>
        </section>
        <section id="pricing" className="pricing">
          <div className="section-heading">
            <span className="eyebrow">A SIMPLE PLACE TO START</span>
            <h2>Your workflow. Your pace.</h2>
            <p>
              {plans?.billing_enabled
                ? "Local compilation included in every plan."
                : "Free beta is open. Paid checkout is currently disabled."}
            </p>
          </div>
          <Notice error={error} />
          <div className="pricing-grid">
            {plans?.plans.map((plan) => (
              <article
                key={plan.tier}
                className={
                  plan.tier === "pro"
                    ? "pricing-card highlighted"
                    : "pricing-card"
                }
              >
                <span className="eyebrow">{plan.tier.toUpperCase()}</span>
                <h3>
                  {money(plan.amount_paise)}
                  <small>{plan.tier === "pro" ? "/ month" : ""}</small>
                </h3>
                {plan.tier === "pro" && !plans.billing_enabled && (
                  <span className="pill">PLANNED PRICING</span>
                )}
                <ul>
                  <li>
                    <Check size={16} />
                    {plan.daily_ai_limit} AI requests per day when configured
                  </li>
                  <li>
                    <Check size={16} />
                    Local prompt compilation
                  </li>
                  <li>
                    <Check size={16} />
                    Six core presets & saved prompts
                  </li>
                  {plan.custom_presets && (
                    <li>
                      <Check size={16} />
                      Custom presets
                    </li>
                  )}
                </ul>
                <Button
                  variant={plan.tier === "pro" ? "default" : "outline"}
                  asChild
                >
                  <Link
                    to={
                      plan.tier === "pro" && plans.billing_enabled
                        ? "/settings"
                        : "/signup"
                    }
                  >
                    {plan.tier === "pro" && !plans.billing_enabled
                      ? "Join the free beta"
                      : plan.tier === "pro"
                        ? "Explore Pro"
                        : "Start free"}{" "}
                    <ArrowRight />
                  </Link>
                </Button>
              </article>
            ))}
          </div>
          <p className="pricing-footnote">
            AI refinement requires a configured provider. Quotas reset at
            midnight UTC.
          </p>
        </section>
        <section className="closing-cta">
          <span className="eyebrow">MAKE THE NEXT QUESTION COUNT</span>
          <h2>Start with clarity.</h2>
          <Button asChild size="lg">
            <Link to="/signup">
              Open your workspace <ArrowRight />
            </Link>
          </Button>
        </section>
      </main>
      <footer className="public-footer">
        <Brand />
        <span>
          © {new Date().getFullYear()} PromptEngine. Clarity before execution.
        </span>
        <Link to="/login">Sign in</Link>
      </footer>
    </div>
  );
}
