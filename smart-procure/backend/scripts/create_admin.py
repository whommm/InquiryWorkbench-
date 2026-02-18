"""
Create or promote an admin user.

Usage:
  python scripts/create_admin.py --username admin --password your-password --display-name 管理员
"""
from __future__ import annotations

import argparse

from app.auth.utils import get_password_hash
from app.models.database import SessionLocal, User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote admin user")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--display-name", default=None, help="Display name")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user:
            user.password_hash = get_password_hash(args.password)
            user.display_name = args.display_name or user.display_name or user.username
            user.role = "admin"
            db.commit()
            print(f"Updated existing user '{args.username}' to admin.")
            return

        user = User(
            username=args.username,
            password_hash=get_password_hash(args.password),
            display_name=args.display_name or args.username,
            role="admin",
        )
        db.add(user)
        db.commit()
        print(f"Created admin user '{args.username}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
