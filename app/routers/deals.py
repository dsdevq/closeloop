from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.stages import stage_probability, validate_transition
from app.database import get_db
from app.models import Contact, Deal, StageTransition

router = APIRouter(prefix="/deals")


class DealCreate(BaseModel):
    title: str
    contact_id: int
    value: float = 0.0


class DealUpdate(BaseModel):
    title: Optional[str] = None
    value: Optional[float] = None
    contact_id: Optional[int] = None


class DealStageUpdate(BaseModel):
    stage: str


def _to_out(deal: Deal, contact_name: Optional[str] = None) -> dict:
    name = contact_name if contact_name is not None else (
        deal.contact.name if deal.contact else None
    )
    return {
        "id": deal.id,
        "title": deal.title,
        "contact_id": deal.contact_id,
        "contact_name": name,
        "stage": deal.stage,
        "value": deal.value,
        "probability": deal.probability,
        "created_at": deal.created_at,
        "updated_at": deal.updated_at,
    }


@router.post("", status_code=201)
def create_deal(
    body: DealCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    contact = db.query(Contact).filter(Contact.id == body.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    now = clk.now().isoformat()
    prob = stage_probability("lead")
    deal = Deal(
        title=body.title,
        contact_id=body.contact_id,
        stage="lead",
        value=body.value,
        probability=prob,
        created_at=now,
        updated_at=now,
    )
    db.add(deal)
    db.flush()  # get deal.id before inserting transition

    transition = StageTransition(
        deal_id=deal.id,
        from_stage=None,
        to_stage="lead",
        occurred_at=now,
    )
    db.add(transition)
    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.get("")
def list_deals(stage: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Deal)
    if stage is not None:
        query = query.filter(Deal.stage == stage)
    deals = query.all()
    return [_to_out(d) for d in deals]


@router.get("/{deal_id}")
def get_deal(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _to_out(deal)


@router.patch("/{deal_id}/stage")
def update_deal_stage(
    deal_id: int,
    body: DealStageUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
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

    transition = StageTransition(
        deal_id=deal.id,
        from_stage=old_stage,
        to_stage=body.stage,
        occurred_at=now,
    )
    db.add(transition)
    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.patch("/{deal_id}")
def update_deal(
    deal_id: int,
    body: DealUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    updates = body.model_dump(exclude_unset=True)
    if "contact_id" in updates:
        contact = db.query(Contact).filter(Contact.id == updates["contact_id"]).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in updates.items():
        setattr(deal, field, value)
    deal.updated_at = clk.now().isoformat()
    db.commit()
    db.refresh(deal)
    return _to_out(deal)


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    db.delete(deal)
    db.commit()
    return Response(status_code=204)
