from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Deal, PipelineStage, User

router = APIRouter(prefix="/pipeline")


class StageCreate(BaseModel):
    name: str
    position: int
    probability: int = 0


class StageUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None
    probability: Optional[int] = None


def _require_admin_or_manager(user: User) -> None:
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager access required")


def _to_out(s: PipelineStage) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "position": s.position,
        "probability": s.probability,
        "is_default": bool(s.is_default),
        "created_at": s.created_at,
    }


@router.get("/stages")
def list_stages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stages = db.query(PipelineStage).order_by(PipelineStage.position).all()
    return [_to_out(s) for s in stages]


@router.post("/stages", status_code=201)
def create_stage(
    body: StageCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    _require_admin_or_manager(current_user)
    if not (0 <= body.probability <= 100):
        raise HTTPException(status_code=422, detail="probability must be 0–100")
    now = clk.now().isoformat()
    stage = PipelineStage(
        name=body.name,
        position=body.position,
        probability=body.probability,
        is_default=0,
        created_at=now,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return _to_out(stage)


@router.patch("/stages/{stage_id}")
def update_stage(
    stage_id: int,
    body: StageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_or_manager(current_user)
    stage = db.query(PipelineStage).filter(PipelineStage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    updates = body.model_dump(exclude_unset=True)
    if "probability" in updates and not (0 <= updates["probability"] <= 100):
        raise HTTPException(status_code=422, detail="probability must be 0–100")

    for field, value in updates.items():
        setattr(stage, field, value)
    db.commit()
    db.refresh(stage)
    return _to_out(stage)


@router.delete("/stages/{stage_id}", status_code=204)
def delete_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_or_manager(current_user)
    stage = db.query(PipelineStage).filter(PipelineStage.id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    deal_count = db.query(Deal).filter(Deal.stage_id == stage_id).count()
    if deal_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete stage: {deal_count} deal(s) are in this stage",
        )

    db.delete(stage)
    db.commit()
    return Response(status_code=204)
