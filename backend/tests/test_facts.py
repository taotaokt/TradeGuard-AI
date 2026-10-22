import json


def _create_fact_counterparty(client, auth_headers):
    response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Fictional Provenance Systems AG",
            "jurisdiction": "CH",
            "registration_number": "KYB-PROVENANCE-001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_sourced_fact_review_quality_and_assessment_snapshot(client, auth_headers):
    counterparty = _create_fact_counterparty(client, auth_headers)
    evidence = client.post(
        "/api/counterparties/{}/evidence".format(counterparty["id"]),
        headers=auth_headers,
        data={"document_type": "tax_document"},
        files={"file": ("tax-record.pdf", b"%PDF-1.4 fictional tax record", "application/pdf")},
    )
    assert evidence.status_code == 201, evidence.text

    tax_fact_payload = {
        "fact_type": "tax_identifier",
        "value": " CHE-123.456.789 ",
        "source_document_id": evidence.json()["id"],
        "valid_from": "2024-01-01T00:00:00",
    }
    tax_fact = client.post(
        "/api/counterparties/{}/facts".format(counterparty["id"]),
        headers=auth_headers,
        json=tax_fact_payload,
    )
    assert tax_fact.status_code == 201, tax_fact.text
    tax_fact_data = tax_fact.json()
    assert tax_fact_data["value"] == "CHE-123.456.789"
    assert tax_fact_data["normalized_value"] == "che-123.456.789"
    assert tax_fact_data["verification_status"] == "unverified"

    duplicate = client.post(
        "/api/counterparties/{}/facts".format(counterparty["id"]),
        headers=auth_headers,
        json=tax_fact_payload,
    )
    assert duplicate.status_code == 409

    owner_fact = client.post(
        "/api/counterparties/{}/facts".format(counterparty["id"]),
        headers=auth_headers,
        json={
            "fact_type": "beneficial_owner",
            "value": "Fictional Sample Owner",
            "source_url": "https://registry.example.test/companies/kyb-001",
            "expires_at": "2020-01-01T00:00:00",
        },
    )
    assert owner_fact.status_code == 201, owner_fact.text
    owner_fact_data = owner_fact.json()

    no_source = client.post(
        "/api/counterparties/{}/facts".format(counterparty["id"]),
        headers=auth_headers,
        json={"fact_type": "industry_code", "value": "4669"},
    )
    assert no_source.status_code == 422

    listed = client.get(
        "/api/counterparties/{}/facts".format(counterparty["id"]),
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()} == {
        tax_fact_data["id"],
        owner_fact_data["id"],
    }

    first_scan = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={"fact_verification_grace_days": 0},
    )
    assert first_scan.status_code == 201, first_scan.text
    open_issues = client.get(
        "/api/data-quality/issues?status=open&code=DQ_COUNTERPARTY_FACT_UNVERIFIED",
        headers=auth_headers,
    ).json()
    assert {tax_fact_data["id"], owner_fact_data["id"]}.issubset(
        {item["entity_id"] for item in open_issues}
    )

    stale_review = client.post(
        "/api/counterparty-facts/{}/actions".format(tax_fact_data["id"]),
        headers=auth_headers,
        json={
            "action": "verify",
            "rationale": "Deliberately stale fact version for concurrency testing.",
            "expected_version": 99,
        },
    )
    assert stale_review.status_code == 409
    for fact in (tax_fact_data, owner_fact_data):
        reviewed = client.post(
            "/api/counterparty-facts/{}/actions".format(fact["id"]),
            headers=auth_headers,
            json={
                "action": "verify",
                "rationale": "The cited registry evidence supports this fictional company fact.",
                "expected_version": 1,
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["verification_status"] == "verified"
        assert reviewed.json()["version"] == 2

    second_scan = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={"fact_verification_grace_days": 0},
    )
    assert second_scan.status_code == 201, second_scan.text
    expired_issues = client.get(
        "/api/data-quality/issues?status=open&code=DQ_COUNTERPARTY_FACT_EXPIRED",
        headers=auth_headers,
    ).json()
    assert owner_fact_data["id"] in {item["entity_id"] for item in expired_issues}
    resolved_unverified = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_COUNTERPARTY_FACT_UNVERIFIED",
        headers=auth_headers,
    ).json()
    assert {tax_fact_data["id"], owner_fact_data["id"]}.issubset(
        {item["entity_id"] for item in resolved_unverified}
    )

    transaction = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "KYB-FACT-SNAPSHOT-001",
            "product_description": "Fictional precision components",
            "origin_country": "CH",
            "destination_country": "US",
            "amount": "12000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "payment_terms_days": 15,
            "deposit_percentage": "30.00",
            "end_use": "Installation in fictional commercial manufacturing equipment",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "CH",
                    "registration_number": counterparty["registration_number"],
                },
                {"role": "end_user", "name": "Fictional US Buyer", "country": "US"},
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    assessment = client.post(
        "/api/transactions/{}/assessments".format(transaction.json()["id"]),
        headers=auth_headers,
    )
    assert assessment.status_code == 201, assessment.text
    snapshot = json.loads(assessment.json()["screening_snapshot_json"])
    assert snapshot["verified_fact_count"] == 2
    assert {item["id"] for item in snapshot["counterparty_facts"]} == {
        tax_fact_data["id"],
        owner_fact_data["id"],
    }
    assert all(item["source_url"] or item["source_document_id"] for item in snapshot["counterparty_facts"])

    retired = client.post(
        "/api/counterparty-facts/{}/actions".format(owner_fact_data["id"]),
        headers=auth_headers,
        json={
            "action": "retire",
            "rationale": "The expired owner record has been replaced by a newer source.",
            "expected_version": 2,
        },
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "retired"
    assert retired.json()["version"] == 3

    closing_scan = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={"fact_verification_grace_days": 0},
    )
    assert closing_scan.status_code == 201, closing_scan.text
    resolved_expired = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_COUNTERPARTY_FACT_EXPIRED",
        headers=auth_headers,
    ).json()
    assert owner_fact_data["id"] in {item["entity_id"] for item in resolved_expired}

    audit_actions = {
        item["action"]
        for item in client.get("/api/audit-events?limit=200", headers=auth_headers).json()
        if item["object_id"] in {tax_fact_data["id"], owner_fact_data["id"]}
    }
    assert {
        "counterparty_fact.created",
        "counterparty_fact.verify",
        "counterparty_fact.retire",
    }.issubset(audit_actions)


def test_fact_frontend_workspace(client):
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "KYB facts" in frontend.text
    assert "NEW SOURCED FACT" in frontend.text
    javascript = client.get("/static/app.js")
    assert "/facts" in javascript.text
    assert "actOnFact" in javascript.text
