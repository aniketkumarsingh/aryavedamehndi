import { useEffect, useRef, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useLanguage } from "@/lib/useLanguage";
import { cartTotal, clearCart, lineKey, removeFromCart, updateCartQuantity } from "@/lib/cart";
import { useCart } from "@/lib/useCart";
import { cartItemsForAnalytics, track } from "@/lib/analytics";
import { payShopOrder } from "@/lib/shopPayment";
import { INDIAN_STATES } from "@/lib/indianStates";

export default function Cart() {
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useLanguage();
  const items = useCart();
  const [shippingName, setShippingName] = useState("");
  const [shippingPhone, setShippingPhone] = useState("");
  const [shippingAddress, setShippingAddress] = useState("");
  const [shippingState, setShippingState] = useState("");
  const [shippingPincode, setShippingPincode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [config, setConfig] = useState(null);
  const [couponInput, setCouponInput] = useState("");
  const [coupon, setCoupon] = useState("");
  const [quote, setQuote] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState("online");
  const [contactEmail, setContactEmail] = useState(() => {
    try {
      return localStorage.getItem("aryaveda_contact_email") || "";
    } catch {
      return "";
    }
  });
  // One Idempotency-Key per checkout attempt: a double-tap or network retry
  // of the same cart returns the same order instead of placing two.
  const idempotencyKey = useRef(null);

  useEffect(() => {
    api.get("/shop/checkout-config").then(setConfig).catch(() => {});
  }, []);

  // Logged-in shoppers get the server's price (coupon included); others see
  // the delivery rule worked out here until they log in to check out.
  const lines = items.map((i) => ({ product_id: i.product_id, variant_id: i.variant_id || null, quantity: i.quantity }));
  const linesKey = JSON.stringify(lines);
  useEffect(() => {
    if (!user || lines.length === 0) {
      setQuote(null);
      return;
    }
    api
      .post("/shop/quote", { items: lines, coupon_code: coupon || null, payment_method: paymentMethod })
      .then(setQuote)
      .catch(() => setQuote(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, linesKey, coupon, paymentMethod]);

  // A changed cart is a different request, so it gets a fresh key.
  useEffect(() => {
    idempotencyKey.current = null;
  }, [linesKey, coupon, paymentMethod]);

  // COD stopped being available (e.g. the total went over the limit).
  useEffect(() => {
    if (paymentMethod === "cod" && quote && !quote.cod_available) setPaymentMethod("online");
  }, [quote, paymentMethod]);

  useEffect(() => {
    if (user) {
      api
        .get("/users/me")
        .then((me) => {
          setShippingName(me.name || "");
          setShippingPhone(me.phone || "");
        })
        .catch(() => {});
    }
  }, [user]);

  async function checkout() {
    if (!user) {
      router.push("/login");
      return;
    }
    if (!shippingName.trim() || !shippingPhone.trim() || !shippingAddress.trim() || !shippingState) {
      setError("Please fill in your name, phone, delivery address and state.");
      return;
    }
    if (!/^[1-9]\d{5}$/.test(shippingPincode.trim())) {
      setError("Please enter a valid 6-digit PIN code.");
      return;
    }
    if (contactEmail.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contactEmail.trim())) {
      setError("Please check your email address, or leave it empty.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      idempotencyKey.current = idempotencyKey.current || (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
      const email = contactEmail.trim();
      try {
        if (email) localStorage.setItem("aryaveda_contact_email", email);
      } catch {
        /* remembering the email is only a convenience */
      }
      const order = await api.post(
        "/shop/orders",
        {
          shipping_name: shippingName,
          shipping_phone: shippingPhone,
          shipping_address: shippingAddress,
          shipping_state: shippingState,
          shipping_pincode: shippingPincode.trim(),
          contact_email: email || null,
          payment_method: paymentMethod,
          items: lines,
          coupon_code: quote?.coupon_code || null,
        },
        undefined,
        { "Idempotency-Key": idempotencyKey.current }
      );
      track("begin_checkout", { value: order.total_amount, currency: "INR", coupon: order.coupon_code || undefined, payment_type: paymentMethod, items: cartItemsForAnalytics(items) });

      // The order now holds these items (and their stock), so the cart is
      // done with - if payment is interrupted the order page offers "Pay now".
      clearCart();
      idempotencyKey.current = null;
      if (order.payment_method === "online") {
        try {
          await payShopOrder(order);
        } catch {
          // Shown on the order page, which has the retry.
        }
      } else {
        track("purchase", { transaction_id: order.id, value: order.total_amount, currency: "INR", payment_type: "cod", items: cartItemsForAnalytics(items) });
      }
      router.push(`/shop/orders/${order.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function applyCoupon(e) {
    e.preventDefault();
    if (!user) {
      router.push("/login");
      return;
    }
    setCoupon(couponInput.trim().toUpperCase());
  }

  // Without a server quote (logged out), apply the delivery rule locally.
  const itemsTotal = cartTotal(items);
  const localShipping = config && itemsTotal < config.free_shipping_above ? config.shipping_fee : 0;
  const summary = quote || { items_amount: itemsTotal, discount_amount: 0, shipping_fee: localShipping, cod_fee: 0, total_amount: itemsTotal + localShipping };
  const total = summary.total_amount;
  const toFreeShipping = config ? config.free_shipping_above - (summary.items_amount - summary.discount_amount) : 0;

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-5">
      <Head>
        <title>Your Cart — AryaVeda Mehndi</title>
      </Head>
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

      <h1 className="text-2xl">Your Cart</h1>

      {items.length === 0 ? (
        <div className="card p-6 text-center">
          <p className="text-sm text-ink-soft mb-3">Your cart is empty.</p>
          <Link href="/shop" className="btn-primary text-sm">
            Browse Products
          </Link>
        </div>
      ) : (
        <>
          <div className="card p-4 flex flex-col gap-3">
            {items.map((item) => (
              <div key={lineKey(item)} className="flex items-center gap-3 border-b border-line pb-3 last:border-b-0 last:pb-0">
                <img
                  src={item.image_url || "/logo/mark.svg"}
                  alt=""
                  className="h-14 w-14 rounded-lg object-contain bg-ivory border border-line p-1 flex-none"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm truncate">{item.name}</p>
                  {item.variant_label && <p className="text-xs text-ink-soft">{item.variant_label}</p>}
                  <p className="text-xs text-ink-soft">₹{item.price} each</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="chip"
                    onClick={() => updateCartQuantity(lineKey(item), item.quantity - 1)}
                    aria-label="Decrease quantity"
                  >
                    −
                  </button>
                  <span className="text-sm w-6 text-center">{item.quantity}</span>
                  <button
                    className="chip"
                    onClick={() => updateCartQuantity(lineKey(item), item.quantity + 1)}
                    aria-label="Increase quantity"
                  >
                    +
                  </button>
                </div>
                <p className="text-sm font-semibold w-16 text-right">₹{item.price * item.quantity}</p>
                <button className="text-red-700 text-xs" onClick={() => removeFromCart(lineKey(item))}>
                  Remove
                </button>
              </div>
            ))}
            <form onSubmit={applyCoupon} className="flex gap-2 pt-2">
              <input
                className="input text-sm uppercase"
                placeholder={t("cart_coupon_placeholder")}
                aria-label={t("cart_coupon_placeholder")}
                value={couponInput}
                onChange={(e) => setCouponInput(e.target.value)}
              />
              <button className="btn-secondary text-sm whitespace-nowrap" disabled={!couponInput.trim()}>
                {t("cart_coupon_apply")}
              </button>
            </form>
            {quote?.coupon_error && <p className="text-xs text-red-700">{quote.coupon_error}</p>}
            {quote?.coupon_code && (
              <p className="text-xs text-green-800">
                {t("cart_coupon_applied", { code: quote.coupon_code })}{" "}
                <button
                  type="button"
                  className="underline"
                  onClick={() => {
                    setCoupon("");
                    setCouponInput("");
                  }}
                >
                  {t("cart_coupon_remove")}
                </button>
              </p>
            )}
            <div className="flex flex-col gap-1 text-sm pt-2 border-t border-line">
              <div className="flex justify-between"><span>{t("cart_items")}</span><span>₹{summary.items_amount}</span></div>
              {summary.discount_amount > 0 && (
                <div className="flex justify-between text-green-800"><span>{t("cart_discount")}</span><span>−₹{summary.discount_amount}</span></div>
              )}
              <div className="flex justify-between">
                <span>{t("cart_delivery")}</span>
                <span>{summary.shipping_fee > 0 ? `₹${summary.shipping_fee}` : t("cart_free")}</span>
              </div>
              {summary.cod_fee > 0 && (
                <div className="flex justify-between"><span>Cash on Delivery charge</span><span>₹{summary.cod_fee}</span></div>
              )}
              {summary.shipping_fee > 0 && toFreeShipping > 0 && (
                <p className="text-xs text-ink-soft">{t("cart_free_delivery_hint", { amount: Math.ceil(toFreeShipping) })}</p>
              )}
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-line">
              <span className="font-semibold">{t("cart_total")}</span>
              <span className="text-lg font-semibold text-maroon-soft">₹{total}</span>
            </div>
            {config && (
              <p className="text-xs text-ink-soft">
                {paymentMethod === "online" && <>{t("cart_pay_window", { minutes: config.payment_window_minutes })} </>}
                <Link href="/legal/shipping" className="underline">{t("policy_delivery")}</Link> ·{" "}
                <Link href="/legal/refunds" className="underline">{t("policy_refund")}</Link>
              </p>
            )}
          </div>

          <div className="card p-5 flex flex-col gap-3">
            <h2 className="font-semibold">Delivery Details</h2>
            <input className="input" placeholder="Full name" value={shippingName} onChange={(e) => setShippingName(e.target.value)} />
            <input className="input" placeholder="Phone number" value={shippingPhone} onChange={(e) => setShippingPhone(e.target.value)} />
            <textarea
              className="input"
              placeholder="Full delivery address"
              value={shippingAddress}
              onChange={(e) => setShippingAddress(e.target.value)}
            />
            <div className="grid grid-cols-2 gap-3">
              <select className="input" aria-label="State" value={shippingState} onChange={(e) => setShippingState(e.target.value)}>
                <option value="">State</option>
                {INDIAN_STATES.map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
              <input
                className="input"
                inputMode="numeric"
                maxLength={6}
                placeholder="PIN code"
                aria-label="PIN code"
                value={shippingPincode}
                onChange={(e) => setShippingPincode(e.target.value.replace(/\D/g, ""))}
              />
            </div>
            <input
              className="input"
              type="email"
              autoComplete="email"
              placeholder="Email for receipt & invoice (optional)"
              aria-label="Email for receipt and invoice"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
            />

            <fieldset className="flex flex-col gap-2 mt-1">
              <legend className="font-semibold text-sm mb-1">Payment</legend>
              <label className="option-card p-3 flex gap-3 items-start cursor-pointer" aria-pressed={paymentMethod === "online"}>
                <input type="radio" name="payment" className="mt-1" checked={paymentMethod === "online"} onChange={() => setPaymentMethod("online")} />
                <span className="text-sm">
                  <b>Pay online</b>
                  <span className="block text-xs text-ink-soft">UPI, cards, net banking or wallets via Razorpay. Bank and UPI offers appear on the payment screen.</span>
                </span>
              </label>
              {config?.cod_enabled && (
                <label
                  className={`option-card p-3 flex gap-3 items-start ${quote && !quote.cod_available ? "opacity-60" : "cursor-pointer"}`}
                  aria-pressed={paymentMethod === "cod"}
                >
                  <input
                    type="radio"
                    name="payment"
                    className="mt-1"
                    checked={paymentMethod === "cod"}
                    disabled={!user || (quote && !quote.cod_available)}
                    onChange={() => setPaymentMethod("cod")}
                  />
                  <span className="text-sm">
                    <b>Cash on Delivery</b>
                    {config.cod_fee > 0 ? ` (+₹${config.cod_fee})` : ""}
                    <span className="block text-xs text-ink-soft">
                      {quote && !quote.cod_available ? quote.cod_error : user ? "Pay the courier in cash or UPI when your order arrives." : "Log in to choose Cash on Delivery."}
                    </span>
                  </span>
                </label>
              )}
            </fieldset>

            {error && <p className="text-sm text-red-700">{error}</p>}
            <button className="btn-primary" disabled={busy} onClick={checkout}>
              {busy
                ? "Placing order…"
                : !user
                  ? "Log in to Checkout"
                  : paymentMethod === "cod"
                    ? `Place order · pay ₹${total} at delivery`
                    : `Pay ₹${total} & Place Order`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
