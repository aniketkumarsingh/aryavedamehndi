import Link from "next/link";
import { GrievanceOfficer, LegalPage, Section, SellerDetails } from "@/components/Legal";

export default function RefundPolicy() {
  return (
    <LegalPage title="Refund & Cancellation Policy" updated="October 2026">
      <Section title="1. Shop orders — cancelling before dispatch">
        <p>
          You can cancel a shop order yourself from <Link href="/shop/orders" className="underline">My Orders</Link> any
          time before it ships. If you&apos;ve already paid, the full amount is refunded to your original payment method
          straight away; banks usually take 5–7 working days to show it.
        </p>
        <p>
          Orders that aren&apos;t paid for within the payment window shown at checkout are cancelled automatically and
          nothing is charged.
        </p>
      </Section>

      <Section title="2. Shop orders — after delivery">
        <p>
          <b>Henna, hair, skin and other consumable products</b> can&apos;t be returned once delivered, for hygiene and
          safety reasons — unless they arrive damaged, leaking, expired or not what you ordered.
        </p>
        <p>
          <b>Tools, books, décor, textiles and gifts</b> can be returned within 7 days of delivery if unused and in their
          original packaging. Return shipping is paid by you unless the item was faulty or wrong.
        </p>
        <p>
          <b>Damaged, faulty or wrong items:</b> tell us within 48 hours of delivery with photos of the item and
          packaging. We&apos;ll send a free replacement or a full refund, whichever you prefer.
        </p>
        <p>
          Refunds for returns are issued within 7 working days of the item reaching us. Refunds are of the amount you
          actually paid (after any coupon discount); delivery charges are refunded only if the item was faulty or wrong.
        </p>
      </Section>

      <Section title="3. Artist bookings">
        <p>
          You can cancel a booking before the artist starts work. If you paid an advance, it&apos;s refunded in full while
          the artist hasn&apos;t set out yet. Once the artist is on the way or has arrived, the advance is kept to cover
          their travel and time.
        </p>
        <p>
          Payment for the design itself is only taken after the finished work is verified, so there&apos;s nothing to
          refund for a service that didn&apos;t happen. If something went wrong after the work began, please raise a
          report from the booking page and our team will review it.
        </p>
      </Section>

      <Section title="4. How to ask for a refund">
        <p>
          Use the booking or order page, or <Link href="/contact" className="underline">contact us</Link> with your order
          number. If you&apos;re not satisfied with how we handle it, write to our Grievance Officer:
        </p>
        <GrievanceOfficer />
      </Section>

      <Section title="5. Seller details">
        <SellerDetails />
      </Section>
    </LegalPage>
  );
}
