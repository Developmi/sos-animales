#!/usr/bin/env python3
"""CLI utility to generate bcrypt hash for administrator password.

Usage:
    uv run python scripts/hash_admin.py
"""

import getpass
import sys
import bcrypt


def main() -> None:
    print("=== SOS Animales Admin Password Hash Generator ===")
    password = getpass.getpass("Enter administrator password: ")
    if not password:
        print("Error: Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    print("\n✅ Hash generated successfully:")
    print(f"ADMIN_PASSWORD_HASH={hashed}\n")
    print("Copy and paste this line into your local .env file.")


if __name__ == "__main__":
    main()
