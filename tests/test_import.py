"""Tests verifying that CSV and XLSX import endpoints insert rows and return ImportResult."""

import csv
import io

import openpyxl


def _csv_bytes(headers: list[str], row: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerow(row)
    return buf.getvalue().encode()


def test_import_csv_inserts(client):
    ISO_DATE = "2024-01-15"

    # ── CONTACTS ──────────────────────────────────────────────────────────────
    # account_id is a non-auto, non-date required column; empty string → FK
    # failure, so create a real account first.
    acc = client.post("/accounts", json={"name": "Acme Corp"})
    assert acc.status_code == 201
    acc_id = acc.json()["id"]

    # created_at is in _AUTO_FIELDS so the validator doesn't require it, but
    # Contact.created_at is NOT NULL — provide it explicitly.  updated_at is a
    # date field (optional by validator) but also NOT NULL; same treatment.
    contact_bytes = _csv_bytes(
        ["name", "email", "company", "title", "phone", "source",
         "lead_score", "account_id", "owner_id", "created_at", "updated_at"],
        ["Alice Import", "alice@import.test", "Acme", "Engineer",
         "555-0001", "inbound", "0.0", str(acc_id), "1", ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/contacts/import",
        files={"file": ("contacts.csv", contact_bytes, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    contacts = client.get("/contacts").json()
    assert any(c["name"] == "Alice Import" for c in contacts)
    contact_id = next(c["id"] for c in contacts if c["name"] == "Alice Import")

    # ── DEALS ─────────────────────────────────────────────────────────────────
    # Pipeline stages are NOT auto-seeded in tests (no lifespan hook); create
    # one so stage_id FK resolves.
    stage_r = client.post(
        "/pipeline/stages",
        json={"name": "Import Stage", "position": 99, "probability": 50},
    )
    assert stage_r.status_code == 201
    stage_id = stage_r.json()["id"]

    # Deal.created_at and Deal.updated_at are NOT NULL (AGENTS.md gotcha).
    deal_bytes = _csv_bytes(
        ["contact_id", "title", "amount", "currency", "stage", "stage_id",
         "value", "probability", "owner_id", "created_at", "updated_at"],
        [str(contact_id), "Import Deal", "0", "USD", "lead", str(stage_id),
         "1000.0", "0.5", "1", ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/deals/import",
        files={"file": ("deals.csv", deal_bytes, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    deals = client.get("/deals").json()
    assert any(d["title"] == "Import Deal" for d in deals)
    deal_id = next(d["id"] for d in deals if d["title"] == "Import Deal")

    # ── ACTIVITIES ────────────────────────────────────────────────────────────
    # deal_id and contact_id are nullable FKs but empty-string CSV values fail
    # the FK check; use the real IDs from the rows inserted above.
    # body and recurrence_rule are required CSV headers (non-auto, non-date);
    # empty-string values are acceptable since the columns are nullable TEXT.
    activity_bytes = _csv_bytes(
        ["deal_id", "contact_id", "type", "title", "body",
         "recurrence_rule", "owner_id", "created_at", "updated_at"],
        [str(deal_id), str(contact_id), "call", "Import Call", "",
         "", "1", ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/activities/import",
        files={"file": ("activities.csv", activity_bytes, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    activities = client.get("/activities").json()
    assert any(a["title"] == "Import Call" for a in activities)


_XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(headers: list[str], row: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_xlsx_inserts(client):
    ISO_DATE = "2024-01-15"

    # ── CONTACTS ──────────────────────────────────────────────────────────────
    # account_id is a required non-auto, non-date column — create a real account
    # first so the FK resolves; integer cell values avoid the empty-string FK
    # failure that afflicts CSV imports (AGENTS.md gotcha).
    acc = client.post("/accounts", json={"name": "Acme XLSX"})
    assert acc.status_code == 201
    acc_id = acc.json()["id"]

    contact_xlsx = _xlsx_bytes(
        ["name", "email", "company", "title", "phone", "source",
         "lead_score", "account_id", "owner_id", "created_at", "updated_at"],
        ["Alice XLSX", "alice_xlsx@import.test", "Acme", "Engineer",
         "555-0002", "inbound", 0.0, acc_id, 1, ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/contacts/import",
        files={"file": ("contacts.xlsx", contact_xlsx, _XLSX_CT)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    contacts = client.get("/contacts").json()
    assert any(c["name"] == "Alice XLSX" for c in contacts)
    contact_id = next(c["id"] for c in contacts if c["name"] == "Alice XLSX")

    # ── DEALS ─────────────────────────────────────────────────────────────────
    # Pipeline stages are NOT auto-seeded in tests (no lifespan hook); create
    # one so the stage_id FK resolves.
    # Deal.created_at and Deal.updated_at are NOT NULL — always supply them
    # (AGENTS.md gotcha: missing dates become None → NOT NULL violation).
    stage_r = client.post(
        "/pipeline/stages",
        json={"name": "XLSX Stage", "position": 100, "probability": 50},
    )
    assert stage_r.status_code == 201
    stage_id = stage_r.json()["id"]

    deal_xlsx = _xlsx_bytes(
        ["contact_id", "title", "amount", "currency", "stage", "stage_id",
         "value", "probability", "owner_id", "created_at", "updated_at"],
        [contact_id, "XLSX Deal", 0, "USD", "lead", stage_id,
         1000.0, 0.5, 1, ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/deals/import",
        files={"file": ("deals.xlsx", deal_xlsx, _XLSX_CT)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    deals = client.get("/deals").json()
    assert any(d["title"] == "XLSX Deal" for d in deals)
    deal_id = next(d["id"] for d in deals if d["title"] == "XLSX Deal")

    # ── ACTIVITIES ────────────────────────────────────────────────────────────
    # deal_id and contact_id are nullable FKs — pass real integer IDs so the FK
    # check passes.  body and recurrence_rule are required headers (non-auto,
    # non-date) but their values may be None (nullable TEXT columns).
    activity_xlsx = _xlsx_bytes(
        ["deal_id", "contact_id", "type", "title", "body",
         "recurrence_rule", "owner_id", "created_at", "updated_at"],
        [deal_id, contact_id, "call", "XLSX Call", None,
         None, 1, ISO_DATE, ISO_DATE],
    )
    r = client.post(
        "/activities/import",
        files={"file": ("activities.xlsx", activity_xlsx, _XLSX_CT)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] >= 1
    assert body["failed"] == []

    activities = client.get("/activities").json()
    assert any(a["title"] == "XLSX Call" for a in activities)
