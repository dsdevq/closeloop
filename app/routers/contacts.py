import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.history import ContactCreatedEntry, ContactDeletedEntry, ContactUpdatedEntry
from app.core.lead_score import compute_lead_score
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Activity, Contact, Deal, User
from app.services.automations import execute_automation_rules
from app.services.history import record_history

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
    db.flush()  # get contact.id before writing history

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="contact",
        entity_id=contact.id,
        event=ContactCreatedEntry(
            contact_id=contact.id,
            contact_name=contact.name,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

    # Automation rules evaluation — After-Save, same transaction (workflow-automation.md §4).
    execute_automation_rules(
        db,
        trigger_kind="contact_created",
        entity_type="contact",
        entity_snapshot={
            "name": contact.name,
            "email": contact.email,
            "phone": contact.phone,
            "company": contact.company,
            "owner_id": contact.owner_id,
            "lead_score": contact.lead_score,
        },
        actor=current_user,
        clk=clk,
    )

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


_CSV_EXPORT_FIELDS = ["id", "name", "email", "phone", "company", "lead_score", "created_at"]
_CSV_IMPORT_REQUIRED = {"name"}
_VALID_SOURCES = {"referral", "inbound", "outbound", "event", "other"}


@router.get("/export")
def export_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export contacts as a CSV file (respects ownership for reps)."""
    query = _apply_owner_filter(db.query(Contact), current_user)
    contacts = query.all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_EXPORT_FIELDS)
    writer.writeheader()
    for c in contacts:
        writer.writerow({f: getattr(c, f, None) for f in _CSV_EXPORT_FIELDS})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/import")
def import_contacts(
    body: dict,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """
    Import contacts from CSV text.

    Accepts: {"csv": "<csv text>"}.
    Returns: {"imported": N, "errors": [{"row": R, "reason": "..."}, ...]}.
    """
    csv_text = body.get("csv", "")
    if not csv_text:
        raise HTTPException(status_code=422, detail="csv field is required and must not be empty")

    reader = csv.DictReader(io.StringIO(csv_text))
    imported = 0
    errors: list[dict] = []
    now = clk.now().isoformat()

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        name = (row.get("name") or "").strip()
        if not name:
            errors.append({"row": row_num, "reason": "name is required"})
            continue

        email = (row.get("email") or "").strip() or None
        phone = (row.get("phone") or "").strip() or None
        company = (row.get("company") or "").strip() or None
        source = (row.get("source") or "").strip() or None
        if source and source not in _VALID_SOURCES:
            errors.append({"row": row_num, "reason": f"invalid source: {source!r}"})
            continue

        contact = Contact(
            name=name,
            email=email,
            phone=phone,
            company=company,
            source=source,
            lead_score=0.0,
            owner_id=current_user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(contact)
        try:
            db.flush()
            # Salesforce Field History Tracking pattern: write history in same transaction.
            record_history(
                db,
                entity_type="contact",
                entity_id=contact.id,
                event=ContactCreatedEntry(
                    contact_id=contact.id,
                    contact_name=contact.name,
                    actor_id=current_user.id,
                ),
                clk=clk,
            )
            imported += 1
        except IntegrityError:
            db.rollback()
            errors.append({"row": row_num, "reason": f"email already exists: {email}"})

    db.commit()
    return {"imported": imported, "errors": errors}


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

    # Only record history when the payload contains at least one field to update,
    # mirroring update_deal's `if non_structural_updates:` guard (deals.py).
    if updates:
        # Salesforce Field History Tracking pattern: write history in same transaction.
        record_history(
            db,
            entity_type="contact",
            entity_id=contact.id,
            event=ContactUpdatedEntry(
                contact_id=contact.id,
                contact_name=contact.name,
                actor_id=current_user.id,
            ),
            clk=clk,
        )

        # Automation rules evaluation — guarded by same `if updates` as history.
        execute_automation_rules(
            db,
            trigger_kind="contact_updated",
            entity_type="contact",
            entity_snapshot={
                "name": contact.name,
                "email": contact.email,
                "phone": contact.phone,
                "company": contact.company,
                "owner_id": contact.owner_id,
                "lead_score": contact.lead_score,
            },
            actor=current_user,
            clk=clk,
        )

    db.commit()
    db.refresh(contact)
    return _to_out(contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Contact), current_user)
    contact = query.filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Capture name before deletion; entity_id survives as a plain INTEGER
    # (no FK on HistoryEntry.entity_id — see activity-timeline.md §5).
    contact_name = contact.name

    db.delete(contact)

    # Salesforce Field History Tracking pattern: write history in same transaction.
    record_history(
        db,
        entity_type="contact",
        entity_id=contact_id,
        event=ContactDeletedEntry(
            contact_id=contact_id,
            contact_name=contact_name,
            actor_id=current_user.id,
        ),
        clk=clk,
    )

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
