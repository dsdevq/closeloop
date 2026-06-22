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

def test_contacts_import_creates_contacts(client):
    csv_text = "name,email,phone,company\nAlice,alice@x.com,555,Acme\nBob,bob@x.com,,Foo"
    r = client.post("/contacts/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert data["errors"] == []
    # Verify they exist
    contacts = client.get("/contacts").json()
    names = [c["name"] for c in contacts]
    assert "Alice" in names
    assert "Bob" in names


def test_contacts_import_missing_name_yields_error(client):
    csv_text = "name,email\n,bad@x.com"
    r = client.post("/contacts/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert len(data["errors"]) == 1
    assert "name is required" in data["errors"][0]["reason"]


def test_contacts_import_duplicate_email_reported_as_error(client):
    _make_contact(client, name="Alice", email="dup@x.com")
    csv_text = "name,email\nAlice2,dup@x.com"
    r = client.post("/contacts/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert any("dup@x.com" in e["reason"] for e in data["errors"])


def test_contacts_import_invalid_source_reported_as_error(client):
    csv_text = "name,email,source\nAlice,a@x.com,twitter"
    r = client.post("/contacts/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert len(data["errors"]) == 1


def test_contacts_import_partial_success(client):
    csv_text = "name,email\nGood,good@x.com\n,bad@x.com\nAlso Good,also@x.com"
    r = client.post("/contacts/import", json={"csv": csv_text})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert len(data["errors"]) == 1


def test_contacts_import_empty_csv_returns_422(client):
    r = client.post("/contacts/import", json={"csv": ""})
    assert r.status_code == 422


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
