import Link from "next/link";
import SocialMeta from "@/components/SocialMeta";
import { Detail, GrievanceOfficer, LegalPage, Section, SellerDetails } from "@/components/Legal";
import { BUSINESS } from "@/lib/business";

export default function Contact() {
  return (
    <LegalPage title="Contact Us" updated="October 2026">
      <SocialMeta title="Contact AryaVeda Mehndi" description="Get help with bookings, shop orders and refunds." path="/contact" />
      <Section title="Customer care">
        <ul className="list-none flex flex-col gap-1">
          <li>Email: <Detail value={BUSINESS.email} label="Support email" href={`mailto:${BUSINESS.email}`} /></li>
          <li>Phone: <Detail value={BUSINESS.phone} label="Support phone" href={`tel:${BUSINESS.phone}`} /></li>
          {BUSINESS.whatsapp && (
            <li>
              WhatsApp:{" "}
              <a href={`https://wa.me/${BUSINESS.whatsapp}`} target="_blank" rel="noopener noreferrer" className="underline text-maroon-soft">
                Chat with us
              </a>
            </li>
          )}
          <li>Hours: {BUSINESS.hours}</li>
        </ul>
        <p>
          For a booking or shop order, it helps to include its number from{" "}
          <Link href="/my-bookings" className="underline">My Bookings</Link> or{" "}
          <Link href="/shop/orders" className="underline">My Orders</Link>.
        </p>
      </Section>

      <Section title="Grievance Officer">
        <p>If we haven&apos;t resolved your complaint, you can escalate it to our Grievance Officer:</p>
        <GrievanceOfficer />
      </Section>

      <Section title="Business details">
        <SellerDetails />
      </Section>
    </LegalPage>
  );
}
