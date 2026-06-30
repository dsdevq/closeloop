from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Account, Contact, User

router = APIRouter(prefix="/accounts")


class AccountCreate(BaseModel):
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


def _to_out(a: Account, contact_count: int = 0) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "domain": a.domain,
        "industry": a.industry,
        "website": a.website,
        "phone": a.phone,
        "address": a.address,
        "notes": a.notes,
        "owner_id": a.owner_id,
        "contact_count": contact_count,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _apply_owner_filter(query, user: User):
    if user.role == "rep":
        return query.filter(Account.owner_id == user.id)
    return query


@router.post("", status_code=201)
def create_account(
    body: AccountCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    now = clk.now().isoformat()
    account = Account(
        name=body.name,
        domain=body.domain,
        industry=body.industry,
        website=body.website,
        phone=body.phone,
        address=body.address,
        notes=body.notes,
        owner_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _to_out(account)


@router.get("")
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Account), current_user)
    accounts = query.all()
    result = []
    for a in accounts:
        count = db.query(Contact).filter(Contact.account_id == a.id).count()
        result.append(_to_out(a, count))
    return result


@router.get("/{account_id}")
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Account), current_user)
    account = query.filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    contacts = db.query(Contact).filter(Contact.account_id == account_id).all()
    out = _to_out(account, len(contacts))
    out["contacts"] = [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "company": c.company,
        }
        for c in contacts
    ]
    return out


@router.patch("/{account_id}")
def update_account(
    account_id: int,
    body: AccountUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Account), current_user)
    account = query.filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(account, field, value)
    account.updated_at = clk.now().isoformat()
    db.commit()
    db.refresh(account)
    return _to_out(account)


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_owner_filter(db.query(Account), current_user)
    account = query.filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
    return Response(status_code=204)
