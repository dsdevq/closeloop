"""Orchestrate bulk import of CRM entities from CSV or XLSX files.

Partial-commit semantics
------------------------
Processing is row-by-row, not all-or-nothing:

* **Valid, non-duplicate rows** are inserted into the database immediately and
  counted in ``ImportResult.inserted``.
* **Duplicate rows** (detected by ``is_duplicate``) are silently skipped and
  counted in ``ImportResult.skipped``.
* **Invalid rows** (rejected by ``validate_row``) are collected into
  ``ImportResult.failed`` as ``RowError`` objects describing the first failure
  in that row — they are never inserted and do not prevent other rows from
  being processed.

``session.commit()`` is called exactly once, after all rows have been
evaluated, so inserted rows are persisted in a single transaction.  If the
commit itself fails (e.g. a foreign-key constraint the validator did not catch),
the entire batch is rolled back by SQLAlchemy's default behaviour.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.interchange.dedup import is_duplicate
from app.interchange.parse_csv import parse_csv
from app.interchange.parse_xlsx import parse_xlsx
from app.interchange.schemas import ImportResult, RowError
from app.interchange.validate import validate_row
from app.models import Activity, Contact, Deal

_MODEL_MAP: dict[str, type] = {
    "contacts": Contact,
    "deals": Deal,
    "activities": Activity,
}


def import_entity(
    entity: str,
    file_bytes: bytes,
    fmt: str,
    session: Session,
) -> ImportResult:
    """Parse, validate, deduplicate, and insert rows for a single CRM entity.

    Args:
        entity:     Registry key — one of 'contacts', 'deals', 'activities'.
        file_bytes: Raw bytes of the uploaded file.
        fmt:        File format — ``'csv'`` or ``'xlsx'``.
        session:    Active SQLAlchemy session used for dedup queries and inserts.

    Returns:
        :class:`~app.interchange.schemas.ImportResult` with counts of
        inserted/skipped rows and a list of
        :class:`~app.interchange.schemas.RowError` for validation failures.

    Raises:
        ValueError: When *fmt* is not ``'csv'`` or ``'xlsx'``.
    """
    if fmt == "csv":
        rows = parse_csv(file_bytes)
    elif fmt == "xlsx":
        rows = parse_xlsx(file_bytes)
    else:
        raise ValueError(f"unsupported format '{fmt}': expected 'csv' or 'xlsx'")

    model_cls = _MODEL_MAP[entity]
    inserted = 0
    skipped = 0
    failures: list[RowError] = []

    for index, raw in enumerate(rows, start=1):
        record, error = validate_row(entity, index, raw)
        if error is not None:
            failures.append(error)
            continue

        if is_duplicate(entity, record, session):
            skipped += 1
            continue

        # Exclude the auto-generated PK; convert date objects back to ISO-8601
        # strings because all ORM date/datetime columns are declared as String.
        kwargs = {
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in record.items()
            if k != "id"
        }
        session.add(model_cls(**kwargs))
        inserted += 1

    session.commit()

    return ImportResult(
        total=inserted + skipped + len(failures),
        inserted=inserted,
        skipped=skipped,
        failed=failures,
    )
