"""Round-trip tests: export an entity to CSV then re-import the produced file.

Contacts and deals deduplicate on (email) and (title, owner_id) respectively,
so a re-import of an already-present row must produce inserted=0, skipped=1.
Activities have no dedup key, so a re-import inserts a second row (inserted=1).
Each test also asserts the final list contains exactly the expected rows.
"""


def test_roundtrip_identical(client):
    # ── shared ISO date used across all three entities ────────────────────────
    ISO_DATE = "2024-03-01"

    # ── Create supporting fixtures ─────────────────────────────────────────────
    # Account required for contact's account_id FK
    acc_r = client.post("/accounts", json={"name": "Roundtrip Corp"})
    assert acc_r.status_code == 201
    acc_id = acc_r.json()["id"]

    # Pipeline stage required for deal's stage_id FK
    stage_r = client.post(
        "/pipeline/stages",
        json={"name": "Roundtrip Stage", "position": 77, "probability": 40},
    )
    assert stage_r.status_code == 201
    stage_id = stage_r.json()["id"]

    # ── CONTACTS ──────────────────────────────────────────────────────────────
    contact_r = client.post(
        "/contacts",
        json={
            "name": "Round Trip Alice",
            "email": "roundtrip_alice@example.test",
            "company": "Acme",
            "phone": "555-7777",
            "account_id": acc_id,
        },
    )
    assert contact_r.status_code == 201
    contact_id = contact_r.json()["id"]

    # Export contacts to CSV
    exp_r = client.get("/contacts/export?format=csv")
    assert exp_r.status_code == 200
    csv_bytes = exp_r.content

    # Re-import the exported CSV — contact with same email must be skipped
    imp_r = client.post(
        "/contacts/import",
        files={"file": ("contacts.csv", csv_bytes, "text/csv")},
    )
    assert imp_r.status_code == 200
    body = imp_r.json()
    assert body["inserted"] == 0, f"expected 0 inserted, got {body['inserted']}"
    assert body["skipped"] == 1, f"expected 1 skipped, got {body['skipped']}"
    assert body["failed"] == []

    # List must still contain exactly one matching contact
    contacts = client.get("/contacts").json()
    matching = [c for c in contacts if c["email"] == "roundtrip_alice@example.test"]
    assert len(matching) == 1, f"expected 1 contact, found {len(matching)}"
    assert matching[0]["name"] == "Round Trip Alice"
    assert matching[0]["company"] == "Acme"
    assert matching[0]["id"] == contact_id

    # ── DEALS ─────────────────────────────────────────────────────────────────
    deal_r = client.post(
        "/deals",
        json={
            "title": "Roundtrip Deal",
            "contact_id": contact_id,
            "value": 2500.0,
            "stage_id": stage_id,
        },
    )
    assert deal_r.status_code == 201
    deal_id = deal_r.json()["id"]

    # Export deals to CSV
    exp_r = client.get("/deals/export?format=csv")
    assert exp_r.status_code == 200
    deal_csv_bytes = exp_r.content

    # Re-import — deal with same title + owner_id must be skipped
    imp_r = client.post(
        "/deals/import",
        files={"file": ("deals.csv", deal_csv_bytes, "text/csv")},
    )
    assert imp_r.status_code == 200
    body = imp_r.json()
    assert body["inserted"] == 0, f"expected 0 inserted, got {body['inserted']}"
    assert body["skipped"] == 1, f"expected 1 skipped, got {body['skipped']}"
    assert body["failed"] == []

    # List must still contain exactly one matching deal
    deals = client.get("/deals").json()
    matching_deals = [d for d in deals if d["title"] == "Roundtrip Deal"]
    assert len(matching_deals) == 1, f"expected 1 deal, found {len(matching_deals)}"
    assert matching_deals[0]["id"] == deal_id

    # ── ACTIVITIES ────────────────────────────────────────────────────────────
    activity_r = client.post(
        "/activities",
        json={
            "type": "call",
            "title": "Roundtrip Call",
            "contact_id": contact_id,
            "deal_id": deal_id,
        },
    )
    assert activity_r.status_code == 201

    # Export activities to CSV
    exp_r = client.get("/activities/export?format=csv")
    assert exp_r.status_code == 200
    activity_csv_bytes = exp_r.content

    # Re-import — activities never dedup, so the row inserts again
    imp_r = client.post(
        "/activities/import",
        files={"file": ("activities.csv", activity_csv_bytes, "text/csv")},
    )
    assert imp_r.status_code == 200
    body = imp_r.json()
    assert body["inserted"] == 1, f"expected 1 inserted, got {body['inserted']}"
    assert body["skipped"] == 0, f"expected 0 skipped, got {body['skipped']}"
    assert body["failed"] == []

    # List must now contain two activities with this title (original + re-imported)
    activities = client.get("/activities").json()
    matching_acts = [a for a in activities if a["title"] == "Roundtrip Call"]
    assert len(matching_acts) == 2, f"expected 2 activities, found {len(matching_acts)}"
