"""Create a reviewer account for local development.

    python -m app.seed reviewer@example.com "a-strong-password"
"""
import sys
from datetime import date

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import User
from .security import hash_password


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m app.seed <email> <password>")
    email, password = sys.argv[1].lower(), sys.argv[2]
    if len(password) < 8:
        sys.exit("password must be at least 8 characters")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"{email} already exists")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role="reviewer",
                full_name="Care Reviewer",
                date_of_birth=date(1990, 1, 1),
            )
        )
        db.commit()
    print(f"Reviewer created: {email}")


if __name__ == "__main__":
    main()
