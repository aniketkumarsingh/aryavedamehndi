import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import Script from "next/script";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { cartTotal, clearCart, removeFromCart, updateCartQuantity } from "@/lib/cart";
import { useCart } from "@/lib/useCart";

export default function Cart() {
  const router = useRouter();
  const { user } = useAuth();
  const items = useCart();
  const [shippingName, setShippingName] = useState("");
  const [shippingPhone, setShippingPhone] = useState("");
  const [shippingAddress, setShippingAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
    if (!shippingName.trim() || !shippingPhone.trim() || !shippingAddress.trim()) {
      setError("Please fill in your name, phone and delivery address.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const order = await api.post("/shop/orders", {
        shipping_name: shippingName,
        shipping_phone: shippingPhone,
        shipping_address: shippingAddress,
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
      });

      const payOrder = await api.post(`/shop/orders/${order.id}/payment/order`, {});

      if (payOrder.razorpay_key_id === "dev_mode_no_key") {
        await api.post(`/shop/orders/${order.id}/payment/verify`, {
          razorpay_order_id: payOrder.razorpay_order_id,
          razorpay_payment_id: "dev_payment",
          razorpay_signature: "dev",
        });
        clearCart();
        router.push(`/shop/orders/${order.id}`);
        return;
      }

      const rzp = new window.Razorpay({
        key: payOrder.razorpay_key_id,
        amount: Math.round(payOrder.amount * 100),
        currency: payOrder.currency,
        name: "AryaVeda Mehndi",
        description: "Mehndi product order",
        order_id: payOrder.razorpay_order_id,
        handler: async (response) => {
          await api.post(`/shop/orders/${order.id}/payment/verify`, {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          clearCart();
          router.push(`/shop/orders/${order.id}`);
        },
      });
      rzp.open();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const total = cartTotal(items);

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
              <div key={item.product_id} className="flex items-center gap-3 border-b border-line pb-3 last:border-b-0 last:pb-0">
                <img
                  src={item.image_url || "/logo/mark.svg"}
                  alt=""
                  className="h-14 w-14 rounded-lg object-contain bg-ivory border border-line p-1 flex-none"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm truncate">{item.name}</p>
                  <p className="text-xs text-ink-soft">₹{item.price} each</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="chip"
                    onClick={() => updateCartQuantity(item.product_id, item.quantity - 1)}
                    aria-label="Decrease quantity"
                  >
                    −
                  </button>
                  <span className="text-sm w-6 text-center">{item.quantity}</span>
                  <button
                    className="chip"
                    onClick={() => updateCartQuantity(item.product_id, item.quantity + 1)}
                    aria-label="Increase quantity"
                  >
                    +
                  </button>
                </div>
                <p className="text-sm font-semibold w-16 text-right">₹{item.price * item.quantity}</p>
                <button className="text-red-700 text-xs" onClick={() => removeFromCart(item.product_id)}>
                  Remove
                </button>
              </div>
            ))}
            <div className="flex justify-between items-center pt-2">
              <span className="font-semibold">Total</span>
              <span className="text-lg font-semibold text-maroon-soft">₹{total}</span>
            </div>
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
            {error && <p className="text-sm text-red-700">{error}</p>}
            <button className="btn-primary" disabled={busy} onClick={checkout}>
              {busy ? "Placing order…" : user ? `Pay ₹${total} & Place Order` : "Log in to Checkout"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
