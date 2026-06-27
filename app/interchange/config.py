"""Per-entity interchange configuration for bulk import/export.

Maps the string keys 'contacts', 'deals', and 'activities' to typed metadata
that describes which columns exist, which contain date/datetime values, and
which field(s) are used to deduplicate rows during import (match_keys).

Column order mirrors the SQLAlchemy model declaration in app/models.py so that
exported files have a predictable, stable layout.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityConfig:
    """Interchange metadata for a single CRM entity.

    Attributes:
        columns:    Ordered list of DB column names to include in import/export.
        date_fields: Subset of columns that hold ISO-8601 date/datetime strings;
                     used by importers to parse and re-format values correctly.
        match_keys: Fields used to identify an existing row during upsert.
                    An empty list means no deduplication — every row is inserted.
    """

    columns: list[str]
    date_fields: list[str]
    match_keys: list[str]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, EntityConfig] = {
    "contacts": EntityConfig(
        columns=[
            "id",
            "name",
            "email",
            "company",
            "title",
            "phone",
            "source",
            "lead_score",
            "account_id",
            "owner_id",
            "created_at",
            "updated_at",
        ],
        date_fields=["created_at", "updated_at"],
        match_keys=["email"],
    ),
    "deals": EntityConfig(
        columns=[
            "id",
            "contact_id",
            "title",
            "amount",
            "currency",
            "stage",
            "stage_id",
            "value",
            "probability",
            "expected_close_date",
            "owner_id",
            "created_at",
            "updated_at",
            "closed_at",
        ],
        date_fields=["expected_close_date", "created_at", "updated_at", "closed_at"],
        match_keys=["title", "owner_id"],
    ),
    "activities": EntityConfig(
        columns=[
            "id",
            "deal_id",
            "contact_id",
            "type",
            "title",
            "body",
            "due_at",
            "completed_at",
            "recurrence_rule",
            "owner_id",
            "created_at",
            "updated_at",
        ],
        date_fields=["due_at", "completed_at", "created_at", "updated_at"],
        match_keys=[],
    ),
}
