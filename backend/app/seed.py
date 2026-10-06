"""Promote an existing account to reviewer.

Reviewers are ordinary Supabase Auth accounts with `role = 'reviewer'` in the profiles table. The role is stored only
in our database (never in user-editable metadata), so a user cannot grant it to themselves.

    1. Sign up in the app with the reviewer's email, confirm the email, and sign in once.
    2. python -m app.seed promote reviewer@example.com
"""
import sys

from sqlalchemy import select

from .db import SessionLocal
from .models import User


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("promote", "demote"):
        sys.exit("usage: python -m app.seed promote|demote <email>")
    action, email = sys.argv[1], sys.argv[2].lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"No profile for {email}. Sign up and sign in once in the app first.")
        user.role = "reviewer" if action == "promote" else "user"
        db.commit()
    print(f"{email} is now a {'reviewer' if action == 'promote' else 'user'}.")


if __name__ == "__main__":
    main()
