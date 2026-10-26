import { useEffect, useState } from "react";
import Link from "next/link";
import { LegalPage, Section, SellerDetails } from "@/components/Legal";
import { api } from "@/lib/api";

export default function ShippingPolicy() {
  // The delivery charge is set by the admin, so show the live numbers.
  const [config, setConfig] = useState(null);
  useEffect(() => {
    api.get("/shop/checkout-config").then(setConfig).catch(() => {});
  }, []);

  return (
    <LegalPage title="Shipping & Delivery Policy" updated="October 2026">
      <Section title="1. Where we deliver">
        <p>We ship shop orders to addresses across India through courier partners. We don&apos;t ship outside India yet.</p>
      </Section>

      <Section title="2. Delivery charges">
        {config ? (
          <p>
            Delivery is <b>free on orders of ₹{config.free_shipping_above} or more</b> (after any coupon discount). Below
            that, a flat delivery charge of <b>₹{config.shipping_fee}</b> applies. The exact charge is always shown in
            your cart before you pay.
          </p>
        ) : (
          <p>Any delivery charge is shown in your cart before you pay, and delivery is free above a minimum order value.</p>
        )}
      </Section>

      <Section title="3. Dispatch and delivery times">
        <p>
          Orders are usually packed and dispatched within 1–2 working days of payment. Delivery then typically takes 2–5
          working days in metro cities and 4–8 working days elsewhere. Fresh henna paste and cones are packed for the
          journey; please refrigerate them as soon as they arrive.
        </p>
      </Section>

      <Section title="4. Tracking">
        <p>
          Once your order ships, its courier name and tracking number appear on your order page in{" "}
          <Link href="/shop/orders" className="underline">My Orders</Link>, and we send you a notification.
        </p>
      </Section>

      <Section title="5. Problems with delivery">
        <p>
          If a parcel arrives damaged or opened, please take photos and tell us within 48 hours — see our{" "}
          <Link href="/legal/refunds" className="underline">refund policy</Link>. If tracking hasn&apos;t moved for 7 days,{" "}
          <Link href="/contact" className="underline">contact us</Link> and we&apos;ll chase the courier.
        </p>
      </Section>

      <Section title="6. Artist bookings">
        <p>Bookings are services at your location, not shipments; nothing is couriered for them.</p>
      </Section>

      <Section title="7. Seller details">
        <SellerDetails />
      </Section>
    </LegalPage>
  );
}
