import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.filter_ast import evaluate_filter, parse_filter
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Contact, Deal, SavedView, User

router = APIRouter(prefix="/saved-views")

_VALID_ENTITY_TYPES = {"contacts", "deals"}
_VALID_SORT_DIRS = {"asc", "desc"}


class SavedViewCreate(BaseModel):
    name: str
    entity_type: str
    filter_expr: dict
    sort_field: Optional[str] = None
    sort_dir: Optional[str] = "asc"


def _to_out(v: SavedView) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "entity_type": v.entity_type,
        "filter_expr": json.loads(v.filter_expr),
        "sort_field": v.sort_field,
        "sort_dir": v.sort_dir,
        "created_at": v.created_at,
        "updated_at": v.updated_at,
    }


def _contact_to_dict(c: Contact) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "company": c.company,
        "lead_score": c.lead_score,
        "created_at": c.created_at,
        "tags": [ct.tag.name for ct in c.tags],
    }


def _deal_to_dict(d: Deal) -> dict:
    return {
        "id": d.id,
        "contact_id": d.contact_id,
        "title": d.title,
        "amount": d.amount,
        "currency": d.currency,
        "stage": d.stage,
        "value": d.value,
        "probability": d.probability,
        "expected_close_date": d.expected_close_date,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "closed_at": d.closed_at,
        "tags": [dt.tag.name for dt in d.tags],
    }


@router.post("", status_code=201)
def create_saved_view(
    body: SavedViewCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    if body.entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"entity_type must be one of {sorted(_VALID_ENTITY_TYPES)}",
        )
    sort_dir = body.sort_dir or "asc"
    if sort_dir not in _VALID_SORT_DIRS:
        raise HTTPException(
            status_code=422,
            detail="sort_dir must be 'asc' or 'desc'",
        )
    # validate the filter AST is parseable
    try:
        parse_filter(body.filter_expr)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid filter_expr: {exc}") from exc

    now = clk.now().isoformat()
    view = SavedView(
        name=body.name,
        entity_type=body.entity_type,
        filter_expr=json.dumps(body.filter_expr),
        sort_field=body.sort_field,
        sort_dir=sort_dir,
        created_at=now,
        updated_at=now,
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return _to_out(view)


@router.get("")
def list_saved_views(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    views = db.query(SavedView).all()
    return [_to_out(v) for v in views]


@router.get("/{view_id}")
def get_saved_view(
    view_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return _to_out(view)


@router.post("/{view_id}/apply")
def apply_saved_view(
    view_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")

    filter_ast = parse_filter(json.loads(view.filter_expr))

    if view.entity_type == "contacts":
        records: list[dict[str, Any]] = [_contact_to_dict(c) for c in db.query(Contact).all()]
    else:
        records = [_deal_to_dict(d) for d in db.query(Deal).all()]

    matched = [r for r in records if evaluate_filter(filter_ast, r)]

    if view.sort_field:
        reverse = view.sort_dir == "desc"
        matched.sort(
            key=lambda r: (r.get(view.sort_field) is None, r.get(view.sort_field)),
            reverse=reverse,
        )

    return matched


@router.delete("/{view_id}", status_code=204)
def delete_saved_view(
    view_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")
    db.delete(view)
    db.commit()
    return Response(status_code=204)
