import Link from "next/link";

export default function PrivacyPolicy() {
  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-5">
      <h1 className="text-2xl">Privacy Policy</h1>
      <p className="text-xs text-ink-soft">
        Last updated: September 2026. Written in accordance with India&apos;s Digital Personal Data Protection Act, 2023
        (DPDP Act).
      </p>

      <Section title="1. What We Collect">
        Phone number (for login), name, gender, profile photo/avatar, and — only with your explicit consent — date of
        birth, guardian/emergency contact details, government ID and bank details (artists only, for verification and
        payouts). Booking details, location at time of booking, and photos exchanged during a booking (reference
        design, completed design).
      </Section>

      <Section title="2. Why We Collect It">
        To operate the marketplace: verifying who you are, matching you with a suitable artist (including
        gender-based safety matching), calculating distance/ETA, processing payments, preventing fraud (photo-gated
        payment, design matching), and improving safety (activity tracking, reports).
      </Section>

      <Section title="3. Consent">
        Artists explicitly consent before we collect or store sensitive personal data (date of birth, ID proof, bank
        details, emergency contact) — see the consent form on the artist profile page. You can withdraw consent at
        any time, which pauses new bookings until consent is given again. Consumers explicitly consent before we
        store their date of birth, anniversary date and secondary contact details.
      </Section>

      <Section title="4. Who We Share It With">
        Your name/photo/rating is visible to the other party in a booking so they know who they&apos;re dealing with. Real
        phone numbers are kept private via masked calling where available. We share payment details with our payment
        processor (Razorpay) and, for artists using our payout feature, banking details with Razorpay Route to enable
        transfers. We do not sell your data to third parties.
      </Section>

      <Section title="5. How We Protect It">
        Passwords aren&apos;t used — login is phone-OTP only. Uploaded photos are validated to be genuine images before
        storage. Sensitive personal data is gated behind explicit consent. We use industry-standard security
        practices (encrypted connections, access controls) to protect stored data.
      </Section>

      <Section title="6. Your Rights">
        You can view and update most of your profile data directly in the app. You can withdraw consent for
        sensitive-data collection at any time. To request deletion of your account and associated data, contact us
        through the app.
      </Section>

      <Section title="7. Data Retention">
        We retain booking records for as long as needed for dispute resolution, payment reconciliation, and legal
        compliance, and personal profile data for as long as your account is active.
      </Section>

      <Section title="8. Changes">
        We may update this policy as the platform evolves; material changes will be reflected here with an updated
        date.
      </Section>

      <p className="text-sm text-ink-soft">
        See also our <Link href="/legal/terms" className="text-maroon-soft underline">Terms of Service</Link>.
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
