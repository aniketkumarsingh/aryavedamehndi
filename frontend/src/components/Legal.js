import Head from "next/head";
import { BUSINESS } from "@/lib/business";

export function LegalPage({ title, updated, children }) {
  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-5">
      <Head>
        <title>{`${title} — AryaVeda Mehndi`}</title>
      </Head>
      <h1 className="text-2xl">{title}</h1>
      <p className="text-xs text-ink-soft">Last updated: {updated}</p>
      {children}
    </div>
  );
}

export function Section({ title, children }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-2">{title}</h2>
      <div className="text-sm text-ink-soft flex flex-col gap-2">{children}</div>
    </div>
  );
}

/** A business detail, or a highlighted gap if it isn't configured yet. */
export function Detail({ value, label, href }) {
  if (!value) return <mark className="bg-yellow-100 text-ink px-1 rounded">[{label} — to be added]</mark>;
  return href ? <a href={href} className="underline text-maroon-soft">{value}</a> : <span>{value}</span>;
}

export function SellerDetails() {
  return (
    <ul className="list-none flex flex-col gap-1">
      <li>Seller: <Detail value={BUSINESS.legalName} label="Registered business name" /> (brand: AryaVeda Mehndi)</li>
      <li>Registered address: <Detail value={BUSINESS.address} label="Registered address" /></li>
      <li>GSTIN: <Detail value={BUSINESS.gstin} label="GSTIN" /></li>
      <li>Customer care: <Detail value={BUSINESS.email} label="Support email" href={`mailto:${BUSINESS.email}`} /> · <Detail value={BUSINESS.phone} label="Support phone" href={`tel:${BUSINESS.phone}`} /></li>
    </ul>
  );
}

export function GrievanceOfficer() {
  return (
    <ul className="list-none flex flex-col gap-1">
      <li>Grievance Officer: <Detail value={BUSINESS.grievanceName} label="Name" /></li>
      <li>Email: <Detail value={BUSINESS.grievanceEmail} label="Email" href={`mailto:${BUSINESS.grievanceEmail}`} /></li>
      <li>Phone: <Detail value={BUSINESS.grievancePhone} label="Phone" href={`tel:${BUSINESS.grievancePhone}`} /></li>
      <li>We acknowledge complaints within 48 hours and resolve them within one month of receipt.</li>
    </ul>
  );
}
