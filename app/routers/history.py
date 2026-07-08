"""History (audit timeline) pull API.

Entity-scoped retrieval borrowed from HubSpot Timeline API and Attio activity
stream (activity-timeline.md §2.2, §2.3): always filtered to a single entity,
newest-first, with an optional limit.  No creation endpoint — history entries
are written exclusively by trigger wiring in domain routers.

`GET /history?entity_type=deal&entity_id=N[&limit=N]`
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import HistoryEntry, User

router = APIRouter(prefix="/history")

_VALID_ENTITY_TYPES = frozenset({"deal", "contact", "activity"})


def _to_out(entry: HistoryEntry) -> dict:
    return {
        "id": entry.id,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "actor_id": entry.actor_id,
        "actor_name": entry.actor.full_name if entry.actor else None,
        "kind": entry.kind,
        "meta_json": entry.meta_json,
        "occurred_at": entry.occurred_at,
    }


@router.get("")
def list_history(
    entity_type: str,
    entity_id: int,
    limit: Optional[int] = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth gate
):
    """Return history entries for a single entity, newest first.

    Both `entity_type` and `entity_id` are required; 422 if either is missing
    or `entity_type` is not a known value.
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"entity_type must be one of {sorted(_VALID_ENTITY_TYPES)}",
        )
    if limit is not None and limit < 1:
        raise HTTPException(status_code=422, detail="limit must be a positive integer")

    query = (
        db.query(HistoryEntry)
        .options(joinedload(HistoryEntry.actor))
        .filter(
            HistoryEntry.entity_type == entity_type,
            HistoryEntry.entity_id == entity_id,
        )
        .order_by(HistoryEntry.occurred_at.desc())
    )
    if limit is not None:
        query = query.limit(limit)

    return [_to_out(e) for e in query.all()]
