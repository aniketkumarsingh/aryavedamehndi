// Display order + labels for design categories (Package.package_type).
// "festival" holds designs made for one festival (Karwa Chauth, Eid, Navratri...);
// everyday party designs that also suit festivals stay in "party" with occasion tags.
export const CATEGORIES = [
  { key: "bridal", label: "Bridal" },
  { key: "festival", label: "Festival" },
  { key: "party", label: "Party & Festive" },
  { key: "regular", label: "Simple & Daily" },
  { key: "feet", label: "Feet" },
  { key: "kids", label: "Kids" },
  { key: "groom", label: "Groom (Dulha)" },
  { key: "men", label: "Men" },
];

// Filters across categories - keys match backend/app/schemas/catalog.py.
export const STYLES = [
  { key: "rajasthani", label: "Rajasthani & Marwari" },
  { key: "indian", label: "Indian Traditional" },
  { key: "arabic", label: "Arabic" },
  { key: "indo-arabic", label: "Indo-Arabic" },
  { key: "jaal", label: "Jaal (Net)" },
  { key: "mandala", label: "Mandala & Tikki" },
  { key: "jewellery", label: "Jewellery Style" },
  { key: "floral", label: "Floral" },
  { key: "minimal", label: "Minimal" },
  { key: "moroccan", label: "Moroccan & Geometric" },
];

export const COVERAGES = [
  { key: "fingers", label: "Fingers only" },
  { key: "palm", label: "Palm" },
  { key: "back", label: "Back of hand" },
  { key: "forearm", label: "Past the wrist" },
  { key: "elbow", label: "Up to the elbow" },
  { key: "toes", label: "Toes" },
  { key: "foot", label: "Foot & ankle" },
];

export const OCCASIONS = [
  { key: "wedding", label: "Wedding" },
  { key: "engagement", label: "Engagement" },
  { key: "roka", label: "Roka" },
  { key: "sangeet", label: "Sangeet" },
  { key: "haldi", label: "Haldi" },
  { key: "nikah", label: "Nikah" },
  { key: "godh-bharai", label: "Godh Bharai (Baby Shower)" },
  { key: "anniversary", label: "Anniversary" },
  { key: "birthday", label: "Birthday" },
  { key: "party", label: "Party" },
  { key: "everyday", label: "Everyday" },
  { key: "karwa-chauth", label: "Karwa Chauth" },
  { key: "teej", label: "Teej" },
  { key: "eid", label: "Eid ul-Fitr" },
  { key: "eid-ul-adha", label: "Eid ul-Adha (Bakrid)" },
  { key: "raksha-bandhan", label: "Raksha Bandhan" },
  { key: "diwali", label: "Diwali" },
  { key: "navratri", label: "Navratri" },
  { key: "gangaur", label: "Gangaur" },
  { key: "ganesh-chaturthi", label: "Ganesh Chaturthi" },
  { key: "lohri", label: "Lohri" },
  { key: "makar-sankranti", label: "Makar Sankranti" },
  { key: "holi", label: "Holi" },
  { key: "bhai-dooj", label: "Bhai Dooj" },
  { key: "chhath", label: "Chhath Puja" },
  { key: "durga-puja", label: "Durga Puja" },
  { key: "janmashtami", label: "Janmashtami" },
  { key: "onam", label: "Onam" },
  { key: "pongal", label: "Pongal" },
  { key: "christmas", label: "Christmas" },
  { key: "baisakhi", label: "Baisakhi" },
  { key: "gurpurab", label: "Gurpurab" },
  { key: "new-year", label: "New Year" },
  { key: "bihu", label: "Bihu" },
  { key: "valentines", label: "Valentine's Day" },
  { key: "tilak", label: "Tilak Ceremony" },
  { key: "mayra", label: "Mayra / Bhaat" },
  { key: "bridal-shower", label: "Bridal Shower" },
  { key: "kitty-party", label: "Kitty Party" },
  { key: "housewarming", label: "Housewarming" },
];

function labelIn(list, key) {
  return list.find((c) => c.key === key)?.label || (key ? key[0].toUpperCase() + key.slice(1) : "");
}

export const categoryLabel = (key) => labelIn(CATEGORIES, key);
export const styleLabel = (key) => labelIn(STYLES, key);
export const coverageLabel = (key) => labelIn(COVERAGES, key);
export const occasionLabel = (key) => labelIn(OCCASIONS, key);

/** Designs matching every filter that's set ("all" or empty = any). */
export function filterDesigns(designs, { category, style, coverage, occasion } = {}) {
  const any = (v) => !v || v === "all";
  return designs.filter(
    (d) =>
      (any(category) || d.category === category) &&
      (any(style) || d.style === style) &&
      (any(coverage) || d.coverage === coverage) &&
      (any(occasion) || (d.occasions || []).includes(occasion)),
  );
}

/** The options of `list` that at least one design has, in list order. */
export function optionsPresent(designs, list, field) {
  const present = new Set(designs.flatMap((d) => (Array.isArray(d[field]) ? d[field] : [d[field]])));
  return list.filter((o) => present.has(o.key));
}

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function formatPriceRange(min, max) {
  return min === max ? `₹${inr.format(min)}` : `₹${inr.format(min)} – ₹${inr.format(max)}`;
}

export function formatDuration(minutes) {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} hr ${m} min` : `${h} hr`;
}

/** Groups designs by category in CATEGORIES order; unknown categories last. */
export function groupByCategory(designs) {
  const order = CATEGORIES.map((c) => c.key);
  const groups = new Map();
  for (const d of designs) {
    if (!groups.has(d.category)) groups.set(d.category, []);
    groups.get(d.category).push(d);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
}
