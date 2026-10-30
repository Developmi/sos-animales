"""CLI entrypoint for SOS Animales operational commands."""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.shared import maintenance


async def handle_maintenance(args: argparse.Namespace) -> int:
    """Execute maintenance subcommand."""
    action = args.action.lower()

    if action == "on":
        reason = (
            getattr(args, "reason", "") or "Pausa operativa manual por administrador"
        )
        success = await maintenance.set_maintenance_mode(True, reason=reason)
        if success:
            print(f"✓ MODO MANTENIMIENTO ACTIVADO: {reason}")
            return 0
        print("✗ Error: no se pudo activar el modo mantenimiento")
        return 1

    if action == "off":
        success = await maintenance.set_maintenance_mode(False)
        if success:
            print("✓ MODO MANTENIMIENTO DESACTIVADO: Sistema en línea")
            return 0
        print("✗ Error: no se pudo desactivar el modo mantenimiento")
        return 1

    if action == "status":
        info = await maintenance.get_maintenance_info()
        active = info.get("active", False)
        status_str = (
            "ACTIVO (503 Service Unavailable)" if active else "INACTIVO (En línea)"
        )
        source_str = info.get("source", "unknown")
        reason_str = info.get("reason", "N/A")
        print(f"Estado de Mantenimiento: {status_str}")
        print(f"Origen del dato: {source_str}")
        if active and reason_str:
            print(f"Motivo: {reason_str}")
        return 0

    print(f"Acción desconocida: {action}. Use on, off o status.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Herramientas operativas de línea de comandos para SOS Animales",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: maintenance
    maint_parser = subparsers.add_parser(
        "maintenance",
        help="Gestionar el modo mantenimiento de la aplicación",
    )
    maint_parser.add_argument(
        "action",
        choices=["on", "off", "status"],
        help="Acción a ejecutar sobre el modo mantenimiento",
    )
    maint_parser.add_argument(
        "--reason",
        "-r",
        type=str,
        default="",
        help="Motivo opcional del mantenimiento (visible en logs y admin)",
    )

    return parser


async def main(args: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if parsed_args.subcommand == "maintenance":
        return await handle_maintenance(parsed_args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
