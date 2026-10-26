// Seller and grievance-officer details shown on the policy and contact
// pages (required by the Consumer Protection (E-Commerce) Rules, 2020 and
// the IT Rules, 2021, and by Razorpay before it activates an account).
// Set them in the frontend environment; anything missing shows as a
// highlighted "[to be added]" so the gap is obvious before launch.

export const BUSINESS = {
  legalName: process.env.NEXT_PUBLIC_BUSINESS_LEGAL_NAME || "",
  address: process.env.NEXT_PUBLIC_BUSINESS_ADDRESS || "",
  state: process.env.NEXT_PUBLIC_BUSINESS_STATE || "", // state of registration, for GST (CGST+SGST vs IGST)
  gstin: process.env.NEXT_PUBLIC_BUSINESS_GSTIN || "",
  email: process.env.NEXT_PUBLIC_SUPPORT_EMAIL || "",
  phone: process.env.NEXT_PUBLIC_SUPPORT_PHONE || "",
  whatsapp: process.env.NEXT_PUBLIC_SUPPORT_WHATSAPP || "", // digits with country code, e.g. 919876543210
  hours: process.env.NEXT_PUBLIC_SUPPORT_HOURS || "Monday to Saturday, 10 am to 7 pm IST",
  grievanceName: process.env.NEXT_PUBLIC_GRIEVANCE_OFFICER_NAME || "",
  grievanceEmail: process.env.NEXT_PUBLIC_GRIEVANCE_OFFICER_EMAIL || "",
  grievancePhone: process.env.NEXT_PUBLIC_GRIEVANCE_OFFICER_PHONE || "",
};
