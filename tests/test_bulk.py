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

def test_deals_import_creates_deals(client):
    c = _make_contact(client)
    csv_text = f"contact_id,title,value,stage\n{c['id']},Deal A,1000,lead\n{c['id']},Deal B,2000,qualified"
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert data["errors"] == []
    deals = client.get("/deals").json()
    titles = [d["title"] for d in deals]
    assert "Deal A" in titles
    assert "Deal B" in titles


def test_deals_import_missing_title_yields_error(client):
    c = _make_contact(client)
    csv_text = f"contact_id,title\n{c['id']},"
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert "title is required" in data["errors"][0]["reason"]


def test_deals_import_invalid_contact_id_yields_error(client):
    csv_text = "contact_id,title\n9999,Phantom Deal"
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert "contact_id not found" in data["errors"][0]["reason"]


def test_deals_import_invalid_stage_yields_error(client):
    c = _make_contact(client)
    csv_text = f"contact_id,title,stage\n{c['id']},Bad Stage Deal,closing"
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert "invalid stage" in data["errors"][0]["reason"]


def test_deals_import_non_numeric_contact_id_yields_error(client):
    csv_text = "contact_id,title\nabc,Bad Deal"
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert "contact_id must be an integer" in data["errors"][0]["reason"]


def test_deals_import_empty_csv_returns_422(client):
    r = client.post("/deals/import", json={"csv": ""})
    assert r.status_code == 422


def test_deals_import_partial_success(client):
    c = _make_contact(client)
    csv_text = (
        "contact_id,title,value\n"
        f"{c['id']},Good Deal,500\n"
        "9999,Bad Deal,100\n"
        f"{c['id']},Also Good,750"
    )
    r = client.post("/deals/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert len(data["errors"]) == 1
