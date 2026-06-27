"""Generic CSV export for registered CRM entities."""

import csv
import io

from fastapi.responses import StreamingResponse

from app.interchange.config import REGISTRY


def export_csv(entity: str, rows: list[dict]) -> StreamingResponse:
    """Return a StreamingResponse containing a CSV file for the given entity.

    Columns are taken from REGISTRY[entity].columns; extra keys in each row
    dict are silently dropped (extrasaction='ignore').
    """
    config = REGISTRY[entity]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=config.columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity}.csv"},
    )
