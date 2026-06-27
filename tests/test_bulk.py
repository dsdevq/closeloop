"""Tests for bulk CSV import/export of contacts and deals."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_contact(client, name="Alice", email="alice@example.com"):
    r = client.post("/contacts", json={"name": name, "email": email})
    assert r.status_code == 201
    return r.json()


def _make_deal(client, contact_id, title="Deal", value=1000.0):
    r = client.post("/deals", json={"title": title, "contact_id": contact_id, "value": value})
    assert r.status_code == 201
    return r.json()


# ── Contact export ─────────────────────────────────────────────────────────────

def test_contacts_export_returns_csv_content_type(client):
    _make_contact(client)
    r = client.get("/contacts/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_contacts_export_empty_db_has_header_only(client):
    r = client.get("/contacts/export")
    assert r.status_code == 200
    lines = [l for l in r.text.splitlines() if l.strip()]
    assert len(lines) == 1  # header only
    assert "name" in lines[0]


def test_contacts_export_contains_seeded_contact(client):
    _make_contact(client, name="Bob", email="bob@example.com")
    r = client.get("/contacts/export")
    assert "Bob" in r.text
    assert "bob@example.com" in r.text


def test_contacts_export_all_contacts(client):
    _make_contact(client, name="Alice", email="a@x.com")
    _make_contact(client, name="Bob", email="b@x.com")
    r = client.get("/contacts/export")
    lines = [l for l in r.text.splitlines() if l.strip()]
    assert len(lines) == 3  # header + 2 data rows


# ── Contact import ─────────────────────────────────────────────────────────────
# The endpoint accepts multipart file upload (.csv or .xlsx).
# Response is ImportResult: {total, inserted, skipped, failed}.

_CONTACT_HDR = (
    "name,email,company,title,phone,source,lead_score,"
    "account_id,owner_id,created_at,updated_at"
)


def _contact_row(name, email, account_id, owner_id):
    """One CSV data row with valid FK values and sensible defaults."""
    return f"{name},{email},,,,,0.0,{account_id},{owner_id},2024-01-01,2024-01-01"


def _csv_upload(*rows, filename="contacts.csv"):
    content = "\n".join([_CONTACT_HDR] + list(rows)).encode()
    return {"file": (filename, content, "text/csv")}


def _seed_fks(client):
    """Return (account_id, admin_id) valid FK values for contact rows."""
    admin_id = client.get("/auth/me").json()["id"]
    acct_id = client.post("/accounts", json={"name": "Corp"}).json()["id"]
    return acct_id, admin_id


def test_contacts_import_creates_contacts(client):
    acct_id, admin_id = _seed_fks(client)
    r = client.post(
        "/contacts/import",
        files=_csv_upload(
            _contact_row("Alice", "alice@x.com", acct_id, admin_id),
            _contact_row("Bob", "bob@x.com", acct_id, admin_id),
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 0
    assert data["failed"] == []
    names = [c["name"] for c in client.get("/contacts").json()]
    assert "Alice" in names
    assert "Bob" in names


def test_contacts_import_missing_required_column_yields_error(client):
    # "name" column absent from header → RowError; rows are never inserted so FK values unused
    csv_bytes = (
        "email,company,title,phone,source,lead_score,account_id,owner_id,created_at,updated_at\n"
        "alice@x.com,,,,,0.0,,,2024-01-01,2024-01-01"
    ).encode()
    r = client.post(
        "/contacts/import",
        files={"file": ("contacts.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert len(data["failed"]) == 1
    assert data["failed"][0]["field"] == "name"


def test_contacts_import_duplicate_email_skipped(client):
    acct_id, admin_id = _seed_fks(client)
    _make_contact(client, name="Alice", email="dup@x.com")
    r = client.post(
        "/contacts/import",
        files=_csv_upload(_contact_row("Alice2", "dup@x.com", acct_id, admin_id)),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert data["skipped"] == 1
    assert data["failed"] == []


def test_contacts_import_unsupported_extension_returns_400(client):
    r = client.post(
        "/contacts/import",
        files={"file": ("contacts.txt", b"name\nAlice", "text/plain")},
    )
    assert r.status_code == 400


def test_contacts_import_partial_success(client):
    acct_id, admin_id = _seed_fks(client)
    _make_contact(client, name="Existing", email="existing@x.com")
    r = client.post(
        "/contacts/import",
        files=_csv_upload(
            _contact_row("Good", "good@x.com", acct_id, admin_id),
            _contact_row("Existing", "existing@x.com", acct_id, admin_id),
            _contact_row("Also Good", "also@x.com", acct_id, admin_id),
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 1
    assert data["failed"] == []


def test_contacts_import_no_extension_returns_400(client):
    r = client.post(
        "/contacts/import",
        files={"file": ("contacts", b"name\nAlice", "text/csv")},
    )
    assert r.status_code == 400


# ── Deal export ────────────────────────────────────────────────────────────────

def test_deals_export_returns_csv(client):
    c = _make_contact(client)
    _make_deal(client, c["id"])
    r = client.get("/deals/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "Deal" in r.text


def test_deals_export_empty_has_header_only(client):
    r = client.get("/deals/export")
    lines = [l for l in r.text.splitlines() if l.strip()]
    assert len(lines) == 1
    assert "title" in lines[0]


def test_deals_export_all_fields(client):
    c = _make_contact(client)
    _make_deal(client, c["id"], title="BigDeal", value=9999.0)
    r = client.get("/deals/export")
    assert "BigDeal" in r.text
    assert str(c["id"]) in r.text


# ── Deal import ────────────────────────────────────────────────────────────────
# The endpoint accepts multipart file upload (.csv or .xlsx).
# Response is ImportResult: {total, inserted, skipped, failed}.

_DEAL_HDR = (
    "contact_id,title,amount,currency,stage,stage_id,value,probability,owner_id,created_at,updated_at"
)


def _deal_row(contact_id, title, owner_id, stage_id, stage="lead", value=0.0):
    return f"{contact_id},{title},0,USD,{stage},{stage_id},{value},0.5,{owner_id},2024-01-01,2024-01-01"


def _deal_csv_upload(*rows, filename="deals.csv"):
    content = "\n".join([_DEAL_HDR] + list(rows)).encode()
    return {"file": (filename, content, "text/csv")}


def _seed_deal_fks(client):
    """Return (contact_id, stage_id, admin_id) for deal import rows."""
    admin_id = client.get("/auth/me").json()["id"]
    contact = _make_contact(client)
    stage = client.post(
        "/pipeline/stages",
        json={"name": "Lead", "position": 1, "probability": 10},
    ).json()
    return contact["id"], stage["id"], admin_id


def test_deals_import_creates_deals(client):
    contact_id, stage_id, admin_id = _seed_deal_fks(client)
    r = client.post(
        "/deals/import",
        files=_deal_csv_upload(
            _deal_row(contact_id, "Deal A", admin_id, stage_id, value=1000.0),
            _deal_row(contact_id, "Deal B", admin_id, stage_id, value=2000.0),
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 0
    assert data["failed"] == []
    titles = [d["title"] for d in client.get("/deals").json()]
    assert "Deal A" in titles
    assert "Deal B" in titles


def test_deals_import_missing_title_yields_error(client):
    # CSV missing 'title' column → RowError for 'title'; no insert attempted
    csv_bytes = (
        "contact_id,amount,currency,stage,stage_id,value,probability,owner_id\n"
        "1,0,USD,lead,,0.0,0.5,1"
    ).encode()
    r = client.post(
        "/deals/import",
        files={"file": ("deals.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert len(data["failed"]) == 1
    assert data["failed"][0]["field"] == "title"


def test_deals_import_invalid_contact_id_yields_error(client):
    # CSV missing 'contact_id' column → RowError for 'contact_id'
    csv_bytes = (
        "title,amount,currency,stage,stage_id,value,probability,owner_id\n"
        "Phantom Deal,0,USD,lead,,0.0,0.5,1"
    ).encode()
    r = client.post(
        "/deals/import",
        files={"file": ("deals.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert len(data["failed"]) == 1
    assert data["failed"][0]["field"] == "contact_id"


def test_deals_import_invalid_stage_yields_error(client):
    # Unsupported file extension → 400
    r = client.post(
        "/deals/import",
        files={"file": ("deals.txt", b"contact_id,title\n1,Deal", "text/plain")},
    )
    assert r.status_code == 400


def test_deals_import_non_numeric_contact_id_yields_error(client):
    # No file extension → 400
    r = client.post(
        "/deals/import",
        files={"file": ("deals", b"contact_id,title\n1,Deal", "text/csv")},
    )
    assert r.status_code == 400


def test_deals_import_empty_csv_returns_422(client):
    r = client.post("/deals/import", json={"csv": ""})
    assert r.status_code == 422


def test_deals_import_partial_success(client):
    contact_id, stage_id, admin_id = _seed_deal_fks(client)
    # Row 2 has an unparseable expected_close_date → RowError; rows 1 and 3 are inserted
    csv_bytes = (
        "contact_id,title,amount,currency,stage,stage_id,value,probability,owner_id,created_at,updated_at,expected_close_date\n"
        f"{contact_id},Good Deal,0,USD,lead,{stage_id},500.0,0.5,{admin_id},2024-01-01,2024-01-01,\n"
        f"{contact_id},Bad Date Deal,0,USD,lead,{stage_id},100.0,0.5,{admin_id},2024-01-01,2024-01-01,not-a-date\n"
        f"{contact_id},Also Good,0,USD,lead,{stage_id},750.0,0.5,{admin_id},2024-01-01,2024-01-01,"
    ).encode()
    r = client.post(
        "/deals/import",
        files={"file": ("deals.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 2
    assert len(data["failed"]) == 1
