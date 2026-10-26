import { api } from "@/lib/api";
import { track } from "@/lib/analytics";

function trackPurchase(order) {
  track("purchase", {
    transaction_id: order.id,
    value: order.total_amount,
    shipping: order.shipping_fee,
    currency: "INR",
    coupon: order.coupon_code || undefined,
    items: order.items.map((i) => ({
      item_id: i.variant_id || i.product_id,
      item_name: i.product_name,
      item_variant: i.variant_label || undefined,
      price: i.unit_price,
      quantity: i.quantity,
    })),
  });
}

/** Takes payment for a pending shop order: opens Razorpay Checkout (needs
 * checkout.js loaded on the page), or settles straight away in dev mode.
 * Resolves "paid", or "dismissed" if the customer closed the payment
 * window - the order stays pending so they can pay later from its page.
 * Retries reuse the order's Razorpay order, so nothing is duplicated. */
export async function payShopOrder(order) {
  const payOrder = await api.post(`/shop/orders/${order.id}/payment/order`, {});

  if (payOrder.razorpay_key_id === "dev_mode_no_key") {
    await api.post(`/shop/orders/${order.id}/payment/verify`, {
      razorpay_order_id: payOrder.razorpay_order_id,
      razorpay_payment_id: "dev_payment",
      razorpay_signature: "dev",
    });
    trackPurchase(order);
    return "paid";
  }

  if (!window.Razorpay) throw new Error("The payment window couldn't load - check your connection and try again.");
  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: payOrder.razorpay_key_id,
      amount: Math.round(payOrder.amount * 100),
      currency: payOrder.currency,
      name: "AryaVeda Mehndi",
      description: "Mehndi product order",
      order_id: payOrder.razorpay_order_id,
      prefill: { name: order.shipping_name, contact: order.shipping_phone },
      handler: async (response) => {
        try {
          await api.post(`/shop/orders/${order.id}/payment/verify`, {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          trackPurchase(order);
          resolve("paid");
        } catch (e) {
          reject(e);
        }
      },
      modal: { ondismiss: () => resolve("dismissed") },
    });
    rzp.open();
  });
}
