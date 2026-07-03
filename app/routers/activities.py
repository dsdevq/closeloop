import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.history import (
    ActivityCompletedEntry,
    ActivityCreatedEntry,
    ActivityDeletedEntry,
    ActivityUpdatedEntry,
)
from app.core.notifications import MentionEvent, parse_mentions
from app.core.recurrence import expand_rrule
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Activity, Notification, User
from app.services.history import record_history
from app.services.notifications import create_notification, resolve_mentioned_users

router = APIRouter(prefix="/activities")

_VALID_TYPES = {"call", "email", "meeting", "note"}


class ActivityCreate(BaseModel):
    deal_id: Optional[int] = None
    contact_id: Optional[int] = None
    type: str
    title: str
    body: Optional[str] = None
    due_at: Optional[str] = None
    recurrence_rule: Optional[dict] = None


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    due_at: Optional[str] = None
    type: Optional[str] = None
    recurrence_rule: Optional[dict] = None


class ExpandRequest(BaseModel):
    count: int = 1


def _to_out(a: Activity) -> dict:
    rule = None
    if a.recurrence_rule:
        try:
            rule = json.loads(a.recurrence_rule)
        except (ValueError, TypeError):
            rule = None
    return {
        "id": a.id,
        "deal_id": a.deal_id,
        "contact_id": a.contact_id,
        "type": a.type,
        "title": a.title,
        "body": a.body,
        "due_at": a.due_at,
        "completed_at": a.completed_at,
        "recurrence_rule": rule,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _apply_owner_filter(query, user: User):
    """Restrict to user's own activities when role is rep."""
    if user.role == "rep":
        return query.filter(Activity.owner_id == user.id)
    return query


def _emit_mention_notifications(
    db: Session,
    *,
    activity: Activity,
    actor: User,
    clk: Clock,
) -> None:
    """Emit MentionEvent notifications for @mentions found in a note body.

    Zoho @mention / Salesforce Chatter pattern (notifications-engine.md §2.5):
    @tokens are parsed from the note body, resolved to active User rows by
    email local-part, and a MentionEvent is written for each recipient
    (excluding self-mentions).  Does NOT commit — caller owns the transaction.

    Only fires for activities with type == "note"; other activity types
    (call, email, meeting) are silently skipped so reps can write email
    addresses or usernames in body fields without triggering spurious pings.
    """
    if activity.type != "note" or not activity.body:
        return
    tokens = parse_mentions(activity.body)
    if not tokens:
        return
    mentioned = resolve_mentioned_users(db, tokens)
    # Guard: skip users already notified for a mention on this activity so that
    # editing a note (e.g. fixing a typo) doesn't re-ping the same recipient.
    already_notified: set[int] = set(
        row[0]
        for row in db.query(Notification.recipient_id).filter(
            Notification.kind == "mention",
            Notification.entity_type == "activity",
            Notification.entity_id == activity.id,
        ).all()
    )
    snippet = activity.body[:120]
    for user in mentioned:
        if user.id == actor.id or user.id in already_notified:
            continue
        create_notification(
            db,
            recipient_id=user.id,
            event=MentionEvent(
                actor_id=actor.id,
                entity_type="activity",
                entity_id=activity.id,
                snippet=snippet,
            ),
            entity_type="activity",
            entity_id=activity.id,
            clk=clk,
        )


@router.post("", status_code=201)
def create_activity(
    body: ActivityCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    if body.type not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type must be one of {sorted(_VALID_TYPES)}",
        )
    if body.recurrence_rule is not None:
        try:
            expand_rrule(body.recurrence_rule, clk.now(), 0)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid recurrence_rule: {exc}") from exc
    now = clk.now().isoformat()
    activity = Activity(
        deal_id=body.deal_id,
        contact_id=body.contact_id,
        type=body.type,
        title=body.title,
        body=body.body,
        due_at=body.due_at,
        recurrence_rule=json.dumps(body.recurrence_rule) if body.recurrence_rule is not None else None,
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(activity)
    # Flush to get activity.id before emitting notifications and history;
    # neither record_history nor create_notification commit (caller owns transaction).
    db.flush()
    _emit_mention_notifications(db, activity=activity, actor=current_user, clk=clk)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="activity",
        entity_id=activity.id,
        event=ActivityCreatedEntry(
            activity_id=activity.id,
            activity_title=activity.title,
            activity_type=activity.type,
            actor_id=current_user.id,
            deal_id=activity.deal_id,
            contact_id=activity.contact_id,
        ),
        clk=clk,
    )

    db.commit()
    db.refresh(activity)
    return _to_out(activity)


@router.get("")
def list_activities(
    deal_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Activity), current_user)
    if deal_id is not None:
        query = query.filter(Activity.deal_id == deal_id)
    if contact_id is not None:
        query = query.filter(Activity.contact_id == contact_id)
    return [_to_out(a) for a in query.all()]


@router.get("/{activity_id}")
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Activity), current_user)
    a = query.filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _to_out(a)


@router.patch("/{activity_id}")
def update_activity(
    activity_id: int,
    body: ActivityUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Activity), current_user)
    a = query.filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    updates = body.model_dump(exclude_unset=True)
    # Capture before any pops so we know whether the body content was replaced.
    body_was_updated = "body" in updates
    if "type" in updates and updates["type"] not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type must be one of {sorted(_VALID_TYPES)}",
        )
    if "recurrence_rule" in updates:
        rule = updates.pop("recurrence_rule")
        if rule is not None:
            try:
                expand_rrule(rule, clk.now(), 0)
            except (ValueError, KeyError) as exc:
                raise HTTPException(status_code=422, detail=f"invalid recurrence_rule: {exc}") from exc
            a.recurrence_rule = json.dumps(rule)
        else:
            a.recurrence_rule = None
    for field, value in updates.items():
        setattr(a, field, value)
    a.updated_at = clk.now().isoformat()
    # Re-parse @mentions whenever the note body is explicitly updated.
    if body_was_updated:
        _emit_mention_notifications(db, activity=a, actor=current_user, clk=clk)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="activity",
        entity_id=a.id,
        event=ActivityUpdatedEntry(
            activity_id=a.id,
            activity_title=a.title,
            activity_type=a.type,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.post("/{activity_id}/complete")
def complete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Activity), current_user)
    a = query.filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    now = clk.now().isoformat()
    a.completed_at = now
    a.updated_at = now

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="activity",
        entity_id=a.id,
        event=ActivityCompletedEntry(
            activity_id=a.id,
            activity_title=a.title,
            activity_type=a.type,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.delete("/{activity_id}", status_code=204)
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Activity), current_user)
    a = query.filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Capture fields before deletion; entity_id survives as a plain INTEGER
    # (no FK on HistoryEntry.entity_id — see activity-timeline.md §5).
    activity_title = a.title
    activity_type = a.type

    db.delete(a)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="activity",
        entity_id=activity_id,
        event=ActivityDeletedEntry(
            activity_id=activity_id,
            activity_title=activity_title,
            activity_type=activity_type,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    db.commit()
    return Response(status_code=204)


@router.post("/{activity_id}/expand", status_code=201)
def expand_activity(
    activity_id: int,
    body: ExpandRequest,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """
    Generate ``count`` future occurrences of a recurring activity.

    The source activity must have both ``due_at`` and ``recurrence_rule`` set.
    Returns a list of newly created activity rows (not the original).
    """
    query = _apply_owner_filter(db.query(Activity), current_user)
    a = query.filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not a.recurrence_rule:
        raise HTTPException(
            status_code=422, detail="activity has no recurrence_rule"
        )
    if not a.due_at:
        raise HTTPException(
            status_code=422, detail="activity has no due_at; cannot expand recurrence"
        )
    if body.count <= 0:
        raise HTTPException(status_code=422, detail="count must be a positive integer")

    try:
        rule = json.loads(a.recurrence_rule)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"malformed recurrence_rule: {exc}") from exc

    try:
        start = _parse_due_at(a.due_at)
        dates = expand_rrule(rule, start, body.count)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = clk.now().isoformat()
    created: list[Activity] = []
    for dt in dates:
        child = Activity(
            deal_id=a.deal_id,
            contact_id=a.contact_id,
            type=a.type,
            title=a.title,
            body=a.body,
            due_at=dt.isoformat(),
            recurrence_rule=a.recurrence_rule,
            owner_id=a.owner_id,
            created_at=now,
            updated_at=now,
        )
        db.add(child)
        created.append(child)

    db.commit()
    for child in created:
        db.refresh(child)
    return [_to_out(c) for c in created]


def _parse_due_at(ts: str):
    """Parse ISO-8601 due_at into a datetime for recurrence expansion."""
    from datetime import datetime
    dt = datetime.fromisoformat(ts)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
