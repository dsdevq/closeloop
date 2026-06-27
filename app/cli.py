"""CloseLoop management CLI.

Entry point: python -m app.cli <command> [options]
"""

import argparse
import asyncio
import sys

from app.database import SessionLocal
from app.interchange.config import REGISTRY
from app.interchange.export_csv import export_csv
from app.interchange.export_xlsx import export_xlsx
from app.models import Activity, Contact, Deal

_VALID_ENTITIES = ("contacts", "deals", "activities")
_VALID_FORMATS = ("csv", "xlsx")

_ENTITY_MODEL = {
    "contacts": Contact,
    "deals": Deal,
    "activities": Activity,
}


async def _collect_async(async_iter) -> bytes:
    parts = []
    async for chunk in async_iter:
        parts.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
    return b"".join(parts)


def _drain_response(response) -> bytes:
    """Drain a StreamingResponse's async body_iterator into a bytes object."""
    return asyncio.run(_collect_async(response.body_iterator))


def _cmd_export(args: argparse.Namespace) -> int:
    out_path: str = args.out or f"{args.entity}.{args.format}"

    db = SessionLocal()
    try:
        model = _ENTITY_MODEL[args.entity]
        records = db.query(model).all()
        columns = REGISTRY[args.entity].columns
        rows = [{col: getattr(r, col, None) for col in columns} for r in records]
    finally:
        db.close()

    if args.format == "xlsx":
        response = export_xlsx(args.entity, rows)
    else:
        response = export_csv(args.entity, rows)

    content = _drain_response(response)
    with open(out_path, "wb") as fh:
        fh.write(content)

    print(f"Exported {len(rows)} {args.entity} to {out_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="closeloop",
        description="CloseLoop management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    export_parser = subparsers.add_parser("export", help="Export CRM data to a file")
    export_parser.add_argument(
        "entity",
        choices=_VALID_ENTITIES,
        help="Entity type to export",
    )
    export_parser.add_argument(
        "--format",
        default="csv",
        choices=_VALID_FORMATS,
        dest="format",
        help="Output format (default: csv)",
    )
    export_parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Output file path (default: <entity>.<format>)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(1)

    if args.command == "export":
        sys.exit(_cmd_export(args))


if __name__ == "__main__":
    main()
