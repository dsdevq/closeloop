"""Per-entity duplicate detection for bulk import.

Checks whether a parsed row already exists in the database before inserting it.
Each entity type uses its own match strategy, derived from the REGISTRY match_keys:

- contacts:   case-insensitive email match
- deals:      exact title + owner_id match (None owner_id matches NULL rows)
- activities: always False — activities are never deduplicated
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.interchange.config import REGISTRY
from app.models import Contact, Deal


def is_duplicate(entity: str, record: dict, session: Session) -> bool:
    """Return True if a matching row already exists in the database.

    Args:
        entity:  Registry key — one of 'contacts', 'deals', 'activities'.
        record:  Cleaned row dict as produced by validate_row.
        session: Active SQLAlchemy Session used to query the database.

    Returns:
        True when a duplicate is found; False when the row is new or when the
        entity skips deduplication entirely (activities).
    """
    config = REGISTRY[entity]

    # Activities have no match_keys — every row is always inserted.
    if entity == "activities" or not config.match_keys:
        return False

    if entity == "contacts":
        email = record.get("email") or ""
        return (
            session.query(Contact)
            .filter(func.lower(Contact.email) == email.lower())
            .first()
            is not None
        )

    if entity == "deals":
        title = record.get("title") or ""
        owner_id = record.get("owner_id")
        return (
            session.query(Deal)
            .filter(
                Deal.title == title,
                Deal.owner_id == owner_id,
            )
            .first()
            is not None
        )

    return False
