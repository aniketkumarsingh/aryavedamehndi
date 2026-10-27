"""What each admin role may do, by request method and path.

    owner    everything, including Settings, the admin team and the audit log
    ops      day-to-day running: orders, shipping, returns and refunds, payments,
             products, artists/KYC, bookings, growth - not Settings changes,
             the team or the audit log
    support  read-only, plus what a support desk needs: notes on orders,
             approving/rejecting returns, answering delivery failures (NDR),
             moderating reviews and resolving reports. No payments, no KYC
             documents, no Settings

The first matching rule wins. Applied by require_role() to every endpoint an
admin reaches, so a new admin endpoint is read-for-all / write-for-owner+ops
until a rule here says otherwise.
"""

import re

ROLES = ("owner", "ops", "support")
ALL = frozenset(ROLES)
OWNER_OPS = frozenset({"owner", "ops"})
OWNER = frozenset({"owner"})
READ = frozenset({"GET", "HEAD", "OPTIONS"})
WRITE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ANY = READ | WRITE

RULES: list[tuple[frozenset, re.Pattern, frozenset]] = [
    (ANY, re.compile(r"^/admin/(team|audit)(/|$)"), OWNER),
    (WRITE, re.compile(r"^/admin/settings(/|$)"), OWNER),
    (ANY, re.compile(r"^/admin/(settings|payments)(/|$)"), OWNER_OPS),
    (ANY, re.compile(r"^/admin/artists/pending-kyc"), OWNER_OPS),  # identity documents
    (WRITE, re.compile(r"^/admin/notes(/|$)"), ALL),
    (WRITE, re.compile(r"^/admin/returns/[^/]+/(approve|reject)$"), ALL),
    (WRITE, re.compile(r"^/admin/shipping/shipments/[^/]+/ndr-action$"), ALL),
    (WRITE, re.compile(r"^/admin/(product-reviews|reports)/"), ALL),
    (READ, re.compile(r".*"), ALL),
    (WRITE, re.compile(r".*"), OWNER_OPS),
]


def effective_role(admin_role: str | None) -> str:
    # Admins from before roles existed (and the seeded admin) are owners.
    return admin_role if admin_role in ROLES else "owner"


def allowed(admin_role: str | None, method: str, path: str) -> bool:
    role = effective_role(admin_role)
    for methods, pattern, roles in RULES:
        if method.upper() in methods and pattern.search(path):
            return role in roles
    return False
