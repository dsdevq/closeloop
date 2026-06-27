"""Per-entity row validation for bulk import.

Validates a single parsed row dict against the entity's interchange config,
checking for missing required fields and coercing date-field values to Python
date objects.  Returns either a cleaned record dict or a RowError describing
the first failure — never both.
"""

from datetime import date, datetime

from app.interchange.config import REGISTRY
from app.interchange.schemas import RowError

# Fields that are auto-generated and are never required in an import payload.
_AUTO_FIELDS = frozenset({"id", "created_at"})


def validate_row(
    entity: str,
    index: int,
    raw: dict,
) -> tuple[dict | None, RowError | None]:
    """Validate one raw parsed row against the entity's interchange config.

    Args:
        entity: Registry key — one of 'contacts', 'deals', 'activities'.
        index:  Zero-based row index carried into any returned RowError.
        raw:    Dict of {column_name: value} from the upstream parser.

    Returns:
        ``(record, None)`` on success, where *record* contains only the columns
        declared in ``config.columns`` and date-field values are coerced to
        :class:`datetime.date` objects.

        ``(None, RowError)`` on the first validation failure encountered.
    """
    config = REGISTRY[entity]

    # Required columns: everything that is not auto-generated and not a date field.
    # Date fields are always optional (they may be absent or blank in the source).
    required_cols = [
        col for col in config.columns
        if col not in _AUTO_FIELDS and col not in config.date_fields
    ]

    for col in required_cols:
        if col not in raw:
            return None, RowError(
                row_index=index,
                field=col,
                value="",
                rule=f"required field '{col}' is missing",
            )

    record: dict = {}
    for col in config.columns:
        val = raw.get(col)
        if col in config.date_fields:
            if not val:
                record[col] = None
            else:
                parsed = _parse_date(str(val))
                if parsed is None:
                    return None, RowError(
                        row_index=index,
                        field=col,
                        value=str(val),
                        rule=(
                            f"field '{col}' has an unparseable date value; "
                            "expected ISO 8601 (e.g. '2024-01-15')"
                        ),
                    )
                record[col] = parsed
        else:
            record[col] = val

    return record, None


def _parse_date(value: str) -> date | None:
    """Parse an ISO 8601 date or datetime string into a :class:`datetime.date`.

    Strips the time portion from datetime strings.  Returns ``None`` when the
    value cannot be parsed.
    """
    # Fast path: plain date string 'YYYY-MM-DD' (also handles longer strings
    # by slicing to the first 10 characters before the time separator).
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        pass
    # Fallback: full datetime string with time zone or time component.
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None
