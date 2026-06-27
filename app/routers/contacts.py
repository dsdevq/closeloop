from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.lead_score import compute_lead_score
from app.database import get_db
from app.dependencies import get_current_user
from app.interchange.config import REGISTRY
from app.interchange.export_csv import export_csv
from app.interchange.export_xlsx import export_xlsx
from app.interchange.import_service import import_entity
from app.interchange.schemas import ImportResult
from app.models import Activity, Contact, Deal, User

router = APIRouter(prefix="/contacts")


class ContactCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    account_id: Optional[int] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    account_id: Optional[int] = None


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
        "account_id": c.account_id,
        "lead_score": c.lead_score,
        "created_at": c.created_at,
    }


def _apply_owner_filter(query, user: User):
    """Restrict to user's own records when role is rep."""
    if user.role == "rep":
        return query.filter(Contact.owner_id == user.id)
    return query


@router.post("", status_code=201)
def create_contact(
    body: ContactCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    now = clk.now().isoformat()
    contact = Contact(
        name=body.name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        account_id=body.account_id,
        lead_score=0.0,
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _to_out(contact)


@router.get("")
def list_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contacts = query.all()
    return [_to_out(c) for c in contacts]


@router.get("/export")
def export_contacts(
    format: str = "csv",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export contacts as CSV or XLSX (respects ownership for reps)."""
    if format not in ("csv", "xlsx"):
        raise HTTPException(status_code=422, detail="format must be 'csv' or 'xlsx'")
    query = _apply_owner_filter(db.query(Contact), current_user)
    contacts = query.all()
    columns = REGISTRY["contacts"].columns
    rows = [{col: getattr(c, col, None) for col in columns} for c in contacts]
    if format == "xlsx":
        return export_xlsx("contacts", rows)
    return export_csv("contacts", rows)


@router.post("/import")
async def import_contacts(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportResult:
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        fmt = "csv"
    elif ext == "xlsx":
        fmt = "xlsx"
    else:
        raise HTTPException(status_code=400, detail="unsupported file type: expected .csv or .xlsx")

    file_bytes = await file.read()
    return import_entity(entity="contacts", file_bytes=file_bytes, fmt=fmt, session=db)


@router.get("/{contact_id}")
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _to_out(contact)


@router.patch("/{contact_id}")
def update_contact(
    contact_id: int,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contact = query.filter(Contact.id == contact_id).first()
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
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contact = query.filter(Contact.id == contact_id).first()
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
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contact = query.filter(Contact.id == contact_id).first()
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
