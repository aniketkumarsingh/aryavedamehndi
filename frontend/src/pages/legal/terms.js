import Link from "next/link";

export default function TermsOfService() {
  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-5">
      <h1 className="text-2xl">Terms of Service</h1>
      <p className="text-xs text-ink-soft">Last updated: September 2026</p>

      <Section title="1. What AryaVeda Mehndi Is">
        AryaVeda Mehndi is a platform that connects consumers with independent, verified mehndi artists for booking
        organic henna services. We are a marketplace — the mehndi service itself is provided by the artist, not by
        us.
      </Section>

      <Section title="2. Accounts &amp; Verification">
        You must verify your phone number via OTP to use the app. Artists must complete KYC verification (ID proof,
        selfie, address proof) and be approved by our team before they can accept bookings. Providing false
        information may result in suspension.
      </Section>

      <Section title="3. Bookings, Negotiation &amp; Cancellation">
        Package prices can be negotiated between consumer and artist within the platform before a booking is
        confirmed. Either party may cancel before the artist starts the service; cancellations after the artist has
        begun work should instead be raised as a report so our team can review what happened.
      </Section>

      <Section title="4. Payments">
        A platform fee is charged for using AryaVeda Mehndi, shown separately at checkout before you pay. Depending
        on the artist, the package amount is either paid directly to the artist outside the app, or collected by us
        alongside the platform fee and forwarded to the artist. Payment for the design only unlocks after the artist
        uploads a photo of the completed work and you confirm it (or it&apos;s automatically verified as matching your
        chosen design).
      </Section>

      <Section title="5. Safety Features">
        We default to matching you with an artist of the same gender, track artist arrival/departure location for
        accountability, and gate payment behind photo verification of the finished design. Masked calling keeps real
        phone numbers private between consumer and artist where available.
      </Section>

      <Section title="6. Reviews, Reports &amp; Suspension">
        Both sides may rate each other after a booking. Reports of misconduct, no-shows or poor quality are reviewed
        by our team; repeated verified issues can lead to an artist being suspended from the platform.
      </Section>

      <Section title="7. Your Responsibilities">
        Provide accurate information, treat the other party respectfully, and use the platform only for its intended
        purpose. Don&apos;t attempt to bypass safety features such as masked calling or the design-verification gate.
      </Section>

      <Section title="8. Limitation of Liability">
        AryaVeda Mehndi facilitates bookings between independent artists and consumers. We are not liable for the
        quality of the mehndi service itself beyond the trust-and-safety mechanisms described above, which we
        maintain in good faith.
      </Section>

      <Section title="9. Changes">
        We may update these terms as the platform evolves. Continued use after a change means you accept the updated
        terms.
      </Section>

      <p className="text-sm text-ink-soft">
        See also our <Link href="/legal/privacy" className="text-maroon-soft underline">Privacy Policy</Link>.
      </p>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-2">{title}</h2>
      <p className="text-sm text-ink-soft">{children}</p>
    </div>
  );
}
