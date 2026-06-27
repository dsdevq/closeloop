"""Smoke tests for the CLI export and import subcommands.

Calls _cmd_export / _cmd_import directly (bypassing HTTP) with SessionLocal
patched to use an isolated in-memory database so no real closeloop.db is touched.
"""
import argparse
import csv
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import _cmd_export, _cmd_import
from app.core.security import hash_password
from app.database import Base
from app.interchange.config import REGISTRY
from app.models import Account, Activity, Contact, Deal, PipelineStage, User

_ISO = "2024-01-15"
_ISO_DT = f"{_ISO}T00:00:00"


# ── In-memory engine ──────────────────────────────────────────────────────────


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


# ── Shared fixture ────────────────────────────────────────────────────────────


@pytest.fixture()
def test_db():
    """In-memory SQLite DB seeded with FK dependencies and one row per entity.

    Yields a dict of integer IDs and the sessionmaker so tests can patch
    app.cli.SessionLocal and create import CSV fixtures with valid FK values.
    """
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    MakeSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    user_id = account_id = contact_id = stage_id = deal_id = None

    with MakeSession() as session:
        user = User(
            email="admin@cli.test",
            hashed_password=hash_password("pass"),
            role="admin",
            full_name="CLI Admin",
            created_at=_ISO_DT,
            is_active=1,
        )
        session.add(user)
        session.flush()
        user_id = user.id

        account = Account(
            name="CLI Corp",
            owner_id=user_id,
            created_at=_ISO_DT,
            updated_at=_ISO_DT,
        )
        session.add(account)
        session.flush()
        account_id = account.id

        contact = Contact(
            name="CLI Contact",
            email="cli@example.com",
            company="CLI Corp",
            title="Engineer",
            phone="555-0001",
            source="inbound",
            lead_score=0.0,
            account_id=account_id,
            owner_id=user_id,
            created_at=_ISO_DT,
            updated_at=_ISO_DT,
        )
        session.add(contact)
        session.flush()
        contact_id = contact.id

        stage = PipelineStage(
            name="CLI Stage",
            position=1,
            probability=50,
            is_default=0,
            created_at=_ISO_DT,
        )
        session.add(stage)
        session.flush()
        stage_id = stage.id

        deal = Deal(
            contact_id=contact_id,
            title="CLI Deal",
            amount=500,
            currency="USD",
            stage="lead",
            stage_id=stage_id,
            value=500.0,
            probability=0.5,
            owner_id=user_id,
            created_at=_ISO_DT,
            updated_at=_ISO_DT,
        )
        session.add(deal)
        session.flush()
        deal_id = deal.id

        activity = Activity(
            deal_id=deal_id,
            contact_id=contact_id,
            type="call",
            title="CLI Call",
            body="",
            owner_id=user_id,
            created_at=_ISO_DT,
            updated_at=_ISO_DT,
        )
        session.add(activity)
        session.commit()

    yield {
        "MakeSession": MakeSession,
        "user_id": user_id,
        "account_id": account_id,
        "contact_id": contact_id,
        "stage_id": stage_id,
        "deal_id": deal_id,
    }
    engine.dispose()


# ── CSV helper ────────────────────────────────────────────────────────────────


def _csv_bytes(headers: list[str], row: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerow(row)
    return buf.getvalue().encode()


# ── Export smoke tests ────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity", ["contacts", "deals", "activities"])
def test_export_csv_creates_file(test_db, tmp_path, entity):
    """export subcommand writes a non-empty CSV for each entity type."""
    out = tmp_path / f"{entity}.csv"
    args = argparse.Namespace(entity=entity, format="csv", out=str(out))

    with patch("app.cli.SessionLocal", test_db["MakeSession"]):
        rc = _cmd_export(args)

    assert rc == 0
    assert out.exists(), f"{entity}.csv was not created"
    assert out.stat().st_size > 0, f"{entity}.csv is empty"
    # Header row must list all configured columns
    first_line = out.read_text().splitlines()[0]
    assert first_line == ",".join(REGISTRY[entity].columns)


@pytest.mark.parametrize("entity", ["contacts", "deals", "activities"])
def test_export_xlsx_creates_file(test_db, tmp_path, entity):
    """export subcommand writes a non-empty XLSX for each entity type."""
    out = tmp_path / f"{entity}.xlsx"
    args = argparse.Namespace(entity=entity, format="xlsx", out=str(out))

    with patch("app.cli.SessionLocal", test_db["MakeSession"]):
        rc = _cmd_export(args)

    assert rc == 0
    assert out.exists(), f"{entity}.xlsx was not created"
    assert out.stat().st_size > 0, f"{entity}.xlsx is empty"


# ── Import smoke tests ────────────────────────────────────────────────────────


def test_import_contacts_csv_inserted(test_db, tmp_path, capsys):
    """import subcommand inserts a new contact row and prints 'inserted=1'."""
    db = test_db
    data = _csv_bytes(
        [
            "name", "email", "company", "title", "phone", "source",
            "lead_score", "account_id", "owner_id", "created_at", "updated_at",
        ],
        [
            "New CLI Contact", "newcli@example.com", "CLI Corp", "Engineer",
            "555-0002", "inbound", "0.0", str(db["account_id"]),
            str(db["user_id"]), _ISO, _ISO,
        ],
    )
    f = tmp_path / "contacts.csv"
    f.write_bytes(data)

    args = argparse.Namespace(entity="contacts", format="csv", file=str(f))
    with patch("app.cli.SessionLocal", db["MakeSession"]):
        rc = _cmd_import(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "inserted" in out
    assert "inserted=1" in out


def test_import_deals_csv_inserted(test_db, tmp_path, capsys):
    """import subcommand inserts a new deal row and prints 'inserted=1'."""
    db = test_db
    data = _csv_bytes(
        [
            "contact_id", "title", "amount", "currency", "stage", "stage_id",
            "value", "probability", "owner_id", "created_at", "updated_at",
        ],
        [
            str(db["contact_id"]), "New CLI Deal", "0", "USD", "lead",
            str(db["stage_id"]), "1000.0", "0.5", str(db["user_id"]),
            _ISO, _ISO,
        ],
    )
    f = tmp_path / "deals.csv"
    f.write_bytes(data)

    args = argparse.Namespace(entity="deals", format="csv", file=str(f))
    with patch("app.cli.SessionLocal", db["MakeSession"]):
        rc = _cmd_import(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "inserted" in out
    assert "inserted=1" in out


def test_import_activities_csv_inserted(test_db, tmp_path, capsys):
    """import subcommand inserts a new activity row and prints 'inserted=1'."""
    db = test_db
    data = _csv_bytes(
        [
            "deal_id", "contact_id", "type", "title", "body",
            "recurrence_rule", "owner_id", "created_at", "updated_at",
        ],
        [
            str(db["deal_id"]), str(db["contact_id"]), "call", "New CLI Call",
            "", "", str(db["user_id"]), _ISO, _ISO,
        ],
    )
    f = tmp_path / "activities.csv"
    f.write_bytes(data)

    args = argparse.Namespace(entity="activities", format="csv", file=str(f))
    with patch("app.cli.SessionLocal", db["MakeSession"]):
        rc = _cmd_import(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "inserted" in out
    assert "inserted=1" in out


# ── Error-path test ───────────────────────────────────────────────────────────


def test_import_missing_required_field_exits_nonzero(test_db, tmp_path, capsys):
    """import subcommand exits with code 1 and prints failed=1 when a required
    field is absent from the CSV header."""
    # 'email' is required for contacts; omitting it causes a validate_row failure.
    bad_data = _csv_bytes(
        ["name", "company"],
        ["Bad Contact", "Corp"],
    )
    f = tmp_path / "bad.csv"
    f.write_bytes(bad_data)

    args = argparse.Namespace(entity="contacts", format="csv", file=str(f))
    with patch("app.cli.SessionLocal", test_db["MakeSession"]):
        rc = _cmd_import(args)

    out = capsys.readouterr().out
    assert rc == 1
    assert "failed=1" in out


def test_import_missing_file_exits_nonzero(test_db, tmp_path, capsys):
    """import subcommand exits with code 1 when the file does not exist."""
    args = argparse.Namespace(
        entity="contacts", format="csv", file=str(tmp_path / "nonexistent.csv")
    )
    with patch("app.cli.SessionLocal", test_db["MakeSession"]):
        rc = _cmd_import(args)

    assert rc == 1
    err = capsys.readouterr().err
    assert "error:" in err
