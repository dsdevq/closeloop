from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.models import Contact, ContactTag, Deal, DealTag, Tag

router = APIRouter(prefix="/tags")


class TagCreate(BaseModel):
    name: str


class TagAssign(BaseModel):
    tag_id: int


def _to_out(tag: Tag) -> dict:
    return {"id": tag.id, "name": tag.name, "created_at": tag.created_at}


# ── Tag CRUD ──────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    tag = Tag(name=body.name.strip(), created_at=clk.now().isoformat())
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"tag name already exists: {body.name!r}")
    db.refresh(tag)
    return _to_out(tag)


@router.get("")
def list_tags(db: Session = Depends(get_db)):
    return [_to_out(t) for t in db.query(Tag).all()]


@router.get("/{tag_id}")
def get_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return _to_out(tag)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return Response(status_code=204)


# ── Contact tags ──────────────────────────────────────────────────────────────

@router.get("/contacts/{contact_id}")
def list_contact_tags(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return [_to_out(ct.tag) for ct in contact.tags]


@router.post("/contacts/{contact_id}", status_code=201)
def add_contact_tag(
    contact_id: int,
    body: TagAssign,
    db: Session = Depends(get_db),
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    tag = db.query(Tag).filter(Tag.id == body.tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    existing = (
        db.query(ContactTag)
        .filter(ContactTag.contact_id == contact_id, ContactTag.tag_id == body.tag_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already assigned to contact")
    db.add(ContactTag(contact_id=contact_id, tag_id=body.tag_id))
    db.commit()
    return _to_out(tag)


@router.delete("/contacts/{contact_id}/{tag_id}", status_code=204)
def remove_contact_tag(contact_id: int, tag_id: int, db: Session = Depends(get_db)):
    ct = (
        db.query(ContactTag)
        .filter(ContactTag.contact_id == contact_id, ContactTag.tag_id == tag_id)
        .first()
    )
    if not ct:
        raise HTTPException(status_code=404, detail="Tag not assigned to this contact")
    db.delete(ct)
    db.commit()
    return Response(status_code=204)


# ── Deal tags ──────────────────────────────────────────────────────────────────

@router.get("/deals/{deal_id}")
def list_deal_tags(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return [_to_out(dt.tag) for dt in deal.tags]


@router.post("/deals/{deal_id}", status_code=201)
def add_deal_tag(
    deal_id: int,
    body: TagAssign,
    db: Session = Depends(get_db),
):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    tag = db.query(Tag).filter(Tag.id == body.tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    existing = (
        db.query(DealTag)
        .filter(DealTag.deal_id == deal_id, DealTag.tag_id == body.tag_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already assigned to deal")
    db.add(DealTag(deal_id=deal_id, tag_id=body.tag_id))
    db.commit()
    return _to_out(tag)


@router.delete("/deals/{deal_id}/{tag_id}", status_code=204)
def remove_deal_tag(deal_id: int, tag_id: int, db: Session = Depends(get_db)):
    dt = (
        db.query(DealTag)
        .filter(DealTag.deal_id == deal_id, DealTag.tag_id == tag_id)
        .first()
    )
    if not dt:
        raise HTTPException(status_code=404, detail="Tag not assigned to this deal")
    db.delete(dt)
    db.commit()
    return Response(status_code=204)
