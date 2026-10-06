import { useEffect, useState } from "react";
import { api, post, errorText } from "@/lib/api";
import { Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
export default function Rewards() {
  const [rewards, setRewards] = useState<{
    referral_url: string;
    registration_days: number;
    conversion_days: number;
  }>();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [redemption, setRedemption] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<typeof rewards>("/api/rewards")
      .then(setRewards)
      .catch((e) => setError(errorText(e)));
  }, []);
  async function redeem() {
    setBusy(true);
    setError("");
    try {
      const r = await post<{
        redemption_id: string;
        discount_type: string;
        message: string;
      }>("/api/rewards/redeem", { code });
      setMessage(r.message);
      setRedemption(
        r.discount_type === "days_extension" ? "" : r.redemption_id,
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function checkout() {
    setBusy(true);
    try {
      const r = await post<{ subscription: { checkout_url: string } }>(
        "/api/billing/subscribe",
        { plan_tier: "pro", redemption_id: redemption },
      );
      const url = new URL(r.subscription.checkout_url);
      if (url.protocol !== "https:" || url.hostname !== "rzp.io")
        throw new Error("Invalid billing link");
      location.assign(url.href);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>Referrals & rewards</h1>
      <Notice error={error} />
      <p role="status">{message}</p>
      <section className="card">
        <h2>Your referral link</h2>
        {rewards && (
          <>
            <a href={rewards.referral_url}>{rewards.referral_url}</a>
            <p>
              Registration rewards: {rewards.registration_days}/30 days. Paid
              conversion rewards: {rewards.conversion_days}/50 days.
            </p>
          </>
        )}
        <p>
          Eligible registrations grant three days; verified paid conversions
          grant ten. Shared IPs or devices and unavailable or matching payment
          fingerprints block automatic rewards.
        </p>
      </section>
      <section className="card">
        <h2>Redeem a coupon</h2>
        <label htmlFor="coupon-code">16-character coupon code</label>
        <Input
          id="coupon-code"
          maxLength={16}
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
        <Button
          disabled={busy || code.length !== 16}
          onClick={() => void redeem()}
        >
          Redeem coupon
        </Button>
        {redemption && (
          <>
            <p>
              The discounted monthly provider plan applies to recurring cycles
              of this subscription.
            </p>
            <Button disabled={busy} onClick={() => void checkout()}>
              Continue to discounted checkout
            </Button>
          </>
        )}
      </section>
    </>
  );
}
