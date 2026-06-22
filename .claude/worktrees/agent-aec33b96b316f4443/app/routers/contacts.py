from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.lead_score import compute_lead_score
from app.database import get_db
from app.models import Activity, Contact, Deal

router = APIRouter(prefix="/contacts")


class ContactCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    company: Optional[str]
    lead_score: float
    created_at: str


def _to_out(c: Contact) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "company": c.company,
        "lead_score": c.lead_score,
        "created_at": c.created_at,
    }


@router.post("", status_code=201)
def create_contact(
    body: ContactCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    now = clk.now().isoformat()
    contact = Contact(
        name=body.name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        lead_score=0.0,
        created_at=now,
        updated_at=now,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _to_out(contact)


@router.get("")
def list_contacts(db: Session = Depends(get_db)):
    contacts = db.query(Contact).all()
    return [_to_out(c) for c in contacts]


@router.get("/{contact_id}")
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _to_out(contact)


@router.patch("/{contact_id}")
def update_contact(
    contact_id: int,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(contact, field, value)
    contact.updated_at = clk.now().isoformat()
    db.commit()
    db.refresh(contact)
    return _to_out(contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return Response(status_code=204)


@router.get("/{contact_id}/lead-score")
def get_lead_score(
    contact_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    deals = db.query(Deal).filter(Deal.contact_id == contact_id).all()
    activities = db.query(Activity).filter(Activity.contact_id == contact_id).all()

    deal_dicts = [{"stage": d.stage, "value": d.value} for d in deals]
    activity_dicts = [{"created_at": a.created_at} for a in activities]
    contact_dict = {"email": contact.email, "phone": contact.phone}

    score = compute_lead_score(contact_dict, deal_dicts, activity_dicts, clock=clk.now)
    contact.lead_score = score
    contact.updated_at = clk.now().isoformat()
    db.commit()

    return {"contact_id": contact_id, "lead_score": score}
