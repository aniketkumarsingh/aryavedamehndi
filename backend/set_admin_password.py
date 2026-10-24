"""Sets (or resets) the username/password for an admin account, for the
POST /auth/admin-login path (http://localhost:3000/admin-login).

Run from backend/:
    venv/bin/python set_admin_password.py <username> [--phone 9999999999]

Prompts for the password (hidden); leave it blank to generate a strong
random one, which is printed once. Also clears any login lockout.
"""

import argparse
import getpass
import secrets
import sys

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User

MIN_LENGTH = 12

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("username")
parser.add_argument("--phone", help="Which admin account (default: the only admin)")
args = parser.parse_args()

db = SessionLocal()
admins = db.query(User).filter(User.role == "admin")
if args.phone:
    admins = admins.filter(User.phone == args.phone)
admins = admins.all()
if len(admins) != 1:
    sys.exit(f"Expected exactly one matching admin, found {len(admins)} - pass --phone to pick one.")
admin = admins[0]

taken = db.query(User).filter(User.username == args.username, User.id != admin.id).first()
if taken:
    sys.exit(f"Username '{args.username}' is already used by another account.")

password = getpass.getpass(f"New password for {args.username} (blank = generate one): ") if sys.stdin.isatty() else ""
generated = not password
if generated:
    password = secrets.token_urlsafe(12)
elif len(password) < MIN_LENGTH:
    sys.exit(f"Use at least {MIN_LENGTH} characters.")

admin.username = args.username
admin.password_hash = hash_password(password)
admin.failed_login_count = 0
admin.locked_until = None
db.commit()

print(f"Admin login set for {admin.name or admin.phone}: username '{args.username}'")
if generated:
    print(f"Generated password (shown once): {password}")
