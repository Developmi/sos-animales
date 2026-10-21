#!/usr/bin/env python3
"""CLI utility to generate bcrypt hash for administrator password.

Usage:
    uv run python scripts/hash_admin.py
"""

import getpass
import sys
from pathlib import Path
import bcrypt


def update_env_file(hashed: str) -> bool:
    """Safely write ADMIN_PASSWORD_HASH to .env file without shell expansion issues."""
    env_path = Path(".env")
    if not env_path.exists():
        return False

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith("ADMIN_PASSWORD_HASH=") or line.startswith(
            "# ADMIN_PASSWORD_HASH="
        ):
            new_lines.append(f"ADMIN_PASSWORD_HASH='{hashed}'")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"ADMIN_PASSWORD_HASH='{hashed}'")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def main() -> None:
    print("==================================================")
    print("🐾 SOS Animales — Admin Password Hash Generator")
    print("==================================================")
    password = getpass.getpass("Ingresa la nueva contraseña de administrador: ")
    if not password:
        print("Error: La contraseña no puede estar vacía.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirma la contraseña: ")
    if password != confirm:
        print("Error: Las contraseñas no coinciden.", file=sys.stderr)
        sys.exit(1)

    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    print("\n✅ Hash bcrypt generado exitosamente (60 caracteres):")
    print(f"ADMIN_PASSWORD_HASH='{hashed}'\n")

    env_file = Path(".env")
    if env_file.exists():
        response = (
            input(
                "¿Deseas guardar este hash directamente en tu archivo .env local? [S/n]: "
            )
            .strip()
            .lower()
        )
        if response in ("", "s", "si", "y", "yes"):
            if update_env_file(hashed):
                print("\n🎉 ¡Actualizado exitosamente en .env!")
                print("Recuerda reiniciar el servicio web para aplicar los cambios:")
                print("  make restart  (o 'docker compose up -d web')\n")
                return

    print("⚠️  IMPORTANTE si lo copias manualmente:")
    print(
        "Debes copiar la línea COMPLETA con COMILLAS SIMPLES para evitar que la terminal"
    )
    print("interprete los signos '$' como variables de entorno:")
    print(f"ADMIN_PASSWORD_HASH='{hashed}'\n")


if __name__ == "__main__":
    main()
