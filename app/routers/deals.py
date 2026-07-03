import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.history import (
    DealAssignedEntry,
    DealCreatedEntry,
    DealDeletedEntry,
    DealStageChangedEntry,
    DealUpdatedEntry,
)
from app.core.notifications import DealAssignedEvent, StageChangedEvent
from app.core.stages import stage_probability, validate_transition
from app.core.velocity import is_deal_rotting, stage_sla_days, time_in_stage_hours
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Contact, Deal, PipelineStage, StageTransition, User
from app.services.history import record_history
from app.services.notifications import create_notification

router = APIRouter(prefix="/deals")


class DealCreate(BaseModel):
    title: str
    contact_id: int
    value: float = 0.0


class DealUpdate(BaseModel):
    title: Optional[str] = None
    value: Optional[float] = None
    contact_id: Optional[int] = None
    stage_id: Optional[int] = None
    probability: Optional[float] = None
    owner_id: Optional[int] = None


class DealStageUpdate(BaseModel):
    stage: str


def _to_out(deal: Deal, contact_name: Optional[str] = None) -> dict:
    name = contact_name if contact_name is not None else (
        deal.contact.name if deal.contact else None
    )
    stage_name = deal.pipeline_stage.name if deal.pipeline_stage else None
    return {
        "id": deal.id,
        "title": deal.title,
        "contact_id": deal.contact_id,
        "contact_name": name,
        "stage": deal.stage,
        "stage_id": deal.stage_id,
        "stage_name": stage_name,
        "value": deal.value,
        "probability": deal.probability,
        "created_at": deal.created_at,
        "updated_at": deal.updated_at,
        "closed_at": deal.closed_at,
    }


def _apply_owner_filter(query, user: User):
    """Restrict to user's own deals when role is rep."""
    if user.role == "rep":
        return query.filter(Deal.owner_id == user.id)
    return query


@router.post("", status_code=201)
def create_deal(
    body: DealCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    contact = db.query(Contact).filter(Contact.id == body.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    first_stage = db.query(PipelineStage).order_by(PipelineStage.position).first()

    now = clk.now().isoformat()
    prob = stage_probability("lead")
    deal = Deal(
        title=body.title,
        contact_id=body.contact_id,
        stage="lead",
        stage_id=first_stage.id if first_stage else None,
        value=body.value,
        probability=prob,
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(deal)
    db.flush()  # get deal.id before inserting transition and history

    transition = StageTransition(
        deal_id=deal.id,
        from_stage=None,
        to_stage="lead",
        occurred_at=now,
    )
    db.add(transition)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="deal",
        entity_id=deal.id,
        event=DealCreatedEntry(
            deal_id=deal.id,
            deal_title=deal.title,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.get("")
def list_deals(
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Deal), current_user)
    if stage is not None:
        query = query.filter(Deal.stage == stage)
    deals = query.all()
    return [_to_out(d) for d in deals]


_DEAL_CSV_EXPORT_FIELDS = ["id", "contact_id", "title", "value", "stage", "currency", "expected_close_date", "created_at"]
_DEAL_VALID_STAGES = {"lead", "qualified", "proposal", "negotiation", "won", "lost"}
_DEAL_CLOSED_STAGES = frozenset({"won", "lost"})


@router.get("/export")
def export_deals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export deals as a CSV file (respects ownership for reps)."""
    query = _apply_owner_filter(db.query(Deal), current_user)
    deals = query.all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_DEAL_CSV_EXPORT_FIELDS)
    writer.writeheader()
    for d in deals:
        writer.writerow({f: getattr(d, f, None) for f in _DEAL_CSV_EXPORT_FIELDS})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deals.csv"},
    )


@router.post("/import")
def import_deals(
    body: dict,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """
    Import deals from CSV text.

    Accepts: {"csv": "<csv text>"}.
    Returns: {"imported": N, "errors": [{"row": R, "reason": "..."}, ...]}.
    Required columns: contact_id, title. Optional: value, stage, currency.
    """
    csv_text = body.get("csv", "")
    if not csv_text:
        raise HTTPException(status_code=422, detail="csv field is required and must not be empty")

    reader = csv.DictReader(io.StringIO(csv_text))
    imported = 0
    errors: list[dict] = []
    now = clk.now().isoformat()

    for row_num, row in enumerate(reader, start=2):
        title = (row.get("title") or "").strip()
        if not title:
            errors.append({"row": row_num, "reason": "title is required"})
            continue

        try:
            contact_id = int(row.get("contact_id") or "")
        except (ValueError, TypeError):
            errors.append({"row": row_num, "reason": "contact_id must be an integer"})
            continue

        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            errors.append({"row": row_num, "reason": f"contact_id not found: {contact_id}"})
            continue

        try:
            value = float(row.get("value") or 0)
        except (ValueError, TypeError):
            errors.append({"row": row_num, "reason": "value must be a number"})
            continue

        stage = (row.get("stage") or "lead").strip()
        if stage not in _DEAL_VALID_STAGES:
            errors.append({"row": row_num, "reason": f"invalid stage: {stage!r}"})
            continue

        currency = (row.get("currency") or "USD").strip()
        prob = stage_probability(stage)

        deal = Deal(
            contact_id=contact_id,
            title=title,
            value=value,
            stage=stage,
            probability=prob,
            currency=currency,
            owner_id=current_user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(deal)
        db.flush()

        transition = StageTransition(
            deal_id=deal.id,
            from_stage=None,
            to_stage=stage,
            occurred_at=now,
        )
        db.add(transition)
        imported += 1

    db.commit()
    return {"imported": imported, "errors": errors}


@router.get("/rotting")
def get_rotting_deals(
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """
    Return all open deals that have been stagnant in their current stage
    longer than the stage SLA.  Each result includes ``days_in_stage``,
    ``sla_days``, and ``is_rotting`` fields appended to the standard deal dict.
    """
    now = clk.now()
    _TERMINAL = {"won", "lost"}
    sla = stage_sla_days()

    query = _apply_owner_filter(db.query(Deal), current_user)
    open_deals = query.filter(Deal.stage.notin_(list(_TERMINAL))).all()
    result = []
    for deal in open_deals:
        trans = [
            {"to_stage": t.to_stage, "from_stage": t.from_stage, "occurred_at": t.occurred_at}
            for t in deal.stage_transitions
        ]
        hours = time_in_stage_hours(trans, deal.stage, now)
        days = round(hours / 24, 1) if hours is not None else None
        rotting = is_deal_rotting(trans, deal.stage, now)
        entry = _to_out(deal)
        entry["days_in_stage"] = days
        entry["sla_days"] = sla.get(deal.stage)
        entry["is_rotting"] = rotting
        result.append(entry)
    return result


@router.get("/{deal_id}")
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Deal), current_user)
    deal = query.filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _to_out(deal)


@router.patch("/{deal_id}/stage")
def update_deal_stage(
    deal_id: int,
    body: DealStageUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Deal), current_user)
    deal = query.filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    try:
        allowed = validate_transition(deal.stage, body.stage)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not allowed:
        raise HTTPException(
            status_code=422,
            detail=f"invalid stage transition: {deal.stage} → {body.stage}",
        )

    now = clk.now().isoformat()
    old_stage = deal.stage
    deal.stage = body.stage
    deal.probability = stage_probability(body.stage)
    deal.updated_at = now
    deal.closed_at = now if body.stage in _DEAL_CLOSED_STAGES else None

    transition = StageTransition(
        deal_id=deal.id,
        from_stage=old_stage,
        to_stage=body.stage,
        occurred_at=now,
    )
    db.add(transition)

    # Salesforce workflow-rule / Pipedrive deal_stage_changed trigger:
    # notify the deal owner when someone else moves the deal to a new stage.
    if body.stage != old_stage and deal.owner_id and deal.owner_id != current_user.id:
        create_notification(
            db,
            recipient_id=deal.owner_id,
            event=StageChangedEvent(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
                from_stage=old_stage,
                to_stage=body.stage,
            ),
            entity_type="deal",
            entity_id=deal.id,
            clk=clk,
        )

    # Salesforce Field History Tracking pattern: record stage change in history.
    if body.stage != old_stage:
        record_history(
            db,
            entity_type="deal",
            entity_id=deal.id,
            event=DealStageChangedEntry(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
                from_stage=old_stage,
                to_stage=body.stage,
            ),
            clk=clk,
        )

    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.patch("/{deal_id}")
def update_deal(
    deal_id: int,
    body: DealUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Deal), current_user)
    deal = query.filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    updates = body.model_dump(exclude_unset=True)

    # Snapshot before-state so triggers can detect what changed.
    old_stage = deal.stage
    old_owner_id = deal.owner_id
    stage_id_in_update = "stage_id" in updates

    if "contact_id" in updates:
        contact = db.query(Contact).filter(Contact.id == updates["contact_id"]).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

    if "owner_id" in updates and updates["owner_id"] is not None:
        new_owner = db.query(User).filter(User.id == updates["owner_id"]).first()
        if not new_owner:
            raise HTTPException(status_code=404, detail="User not found")

    if "stage_id" in updates:
        ps = db.query(PipelineStage).filter(PipelineStage.id == updates["stage_id"]).first()
        if not ps:
            raise HTTPException(status_code=404, detail="Pipeline stage not found")
        deal.stage_id = ps.id
        deal.stage = ps.name
        if "probability" not in updates:
            deal.probability = ps.probability / 100.0
        updates.pop("stage_id")

    for field, value in updates.items():
        setattr(deal, field, value)
    deal.updated_at = clk.now().isoformat()

    # HubSpot automation / Salesforce workflow-rule After-Save trigger:
    # fire StageChangedEvent when stage_id update caused the stage name to change.
    # Use old_owner_id so that when stage and owner both change in one PATCH,
    # the notification goes to whoever owned the deal at the time of the stage change.
    if stage_id_in_update and deal.stage != old_stage:
        recipient = old_owner_id
        if recipient and recipient != current_user.id:
            create_notification(
                db,
                recipient_id=recipient,
                event=StageChangedEvent(
                    deal_id=deal.id,
                    deal_title=deal.title,
                    actor_id=current_user.id,
                    from_stage=old_stage,
                    to_stage=deal.stage,
                ),
                entity_type="deal",
                entity_id=deal.id,
                clk=clk,
            )

    # Salesforce / Pipedrive deal-assigned trigger:
    # fire DealAssignedEvent when owner_id changes to a new user.
    new_owner_id = deal.owner_id
    if new_owner_id and new_owner_id != old_owner_id and new_owner_id != current_user.id:
        create_notification(
            db,
            recipient_id=new_owner_id,
            event=DealAssignedEvent(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
                previous_owner_id=old_owner_id,
            ),
            entity_type="deal",
            entity_id=deal.id,
            clk=clk,
        )

    # Salesforce Field History Tracking pattern: record what changed in history.
    if stage_id_in_update and deal.stage != old_stage:
        record_history(
            db,
            entity_type="deal",
            entity_id=deal.id,
            event=DealStageChangedEntry(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
                from_stage=old_stage,
                to_stage=deal.stage,
            ),
            clk=clk,
        )

    if new_owner_id and new_owner_id != old_owner_id:
        record_history(
            db,
            entity_type="deal",
            entity_id=deal.id,
            event=DealAssignedEntry(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
                from_owner_id=old_owner_id,
                to_owner_id=new_owner_id,
            ),
            clk=clk,
        )

    # Record a generic update entry when non-structural fields changed.
    structural_only = {"stage_id", "owner_id"}
    non_structural_updates = {k for k in updates if k not in structural_only}
    if non_structural_updates:
        record_history(
            db,
            entity_type="deal",
            entity_id=deal.id,
            event=DealUpdatedEntry(
                deal_id=deal.id,
                deal_title=deal.title,
                actor_id=current_user.id,
            ),
            clk=clk,
        )

    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.delete("/{deal_id}", status_code=204)
def delete_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Deal), current_user)
    deal = query.filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Capture title before deletion; entity_id survives as a plain INTEGER
    # (no FK on HistoryEntry.entity_id — see activity-timeline.md §5).
    deal_title = deal.title

    db.delete(deal)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="deal",
        entity_id=deal_id,
        event=DealDeletedEntry(
            deal_id=deal_id,
            deal_title=deal_title,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    db.commit()
    return Response(status_code=204)
