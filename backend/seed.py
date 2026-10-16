"""One-off dev seed: an admin user, a couple of packages, and starter CMS
content, so the app isn't empty on first run.

Run after migrations:  python seed.py
"""

from app.database import SessionLocal
from app.models.cms import CmsContent
from app.models.package import Package
from app.models.user import User

db = SessionLocal()

if not db.query(User).filter(User.role == "admin").first():
    db.add(User(phone="9999999999", name="Arya Admin", role="admin", gender="other"))
    print("Seeded admin user: phone 9999999999 (log in with OTP as normal, dev mode prints the code)")

if not db.query(Package).count():
    db.add_all(
        [
            Package(
                name="Regular Mehndi",
                package_type="regular",
                description="Simple front and back hand designs for everyday occasions (hands only).",
                price_min=300,
                price_max=800,
                duration_minutes=45,
                negotiable=True,
            ),
            Package(
                name="Bridal Mehndi",
                package_type="bridal",
                description="Detailed bridal mehndi covering both hands and feet, with organic henna paste.",
                price_min=4000,
                price_max=15000,
                duration_minutes=240,
                negotiable=True,
            ),
            Package(
                name="Festival Party Mehndi",
                package_type="party",
                description="Medium-detail hand designs for festivals and small get-togethers (hands only).",
                price_min=500,
                price_max=1500,
                duration_minutes=60,
                negotiable=True,
            ),
            Package(
                name="Feet Mehndi",
                package_type="feet",
                description="Mehndi designs for feet only, for anyone who just wants their feet done (no hand designs in this package).",
                price_min=250,
                price_max=700,
                duration_minutes=40,
                negotiable=True,
            ),
        ]
    )
    print("Seeded 3 starter packages")

if db.get(CmsContent, "home.hero") is None:
    db.add(
        CmsContent(
            key="home.hero",
            content={
                "headline": "Ayurvedic Mehndi, Booked Safely, Delivered to Your Door",
                "subheadline": "AryaVeda Mehndi connects you with verified, gender-matched mehndi artists near you - organic henna, transparent pricing, and payment that only releases once you're happy with the design.",
                "cta_label": "Find an Artist Near You",
            },
            updated_by="seed",
        )
    )
    db.add(
        CmsContent(
            key="brand.story",
            content={
                "title": "Why AryaVeda Mehndi",
                "body": "We use only Ayurvedic, organic henna paste - no chemical additives - and every artist on the platform is verified before they can accept a single booking.",
            },
            updated_by="seed",
        )
    )
    print("Seeded starter CMS content")

db.commit()
db.close()
print("Done.")
