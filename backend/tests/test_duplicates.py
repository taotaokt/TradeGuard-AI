import json

from backend.tests.test_api import _create_active_screening_list


def _create_counterparty(client, auth_headers, *, name, registration, website, aliases=None):
    response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": name,
            "jurisdiction": "SG",
            "registration_number": registration,
            "website": website,
            "aliases": aliases or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_duplicate_detection_resolution_and_assessment_routing(client, auth_headers):
    _create_active_screening_list(client, auth_headers, "duplicate-review-list")
    original = _create_counterparty(
        client,
        auth_headers,
        name="Fictional Meridian Industrial Holdings Limited",
        registration="MERIDIAN-001",
        website="https://meridian.example",
    )
    possible_duplicate = _create_counterparty(
        client,
        auth_headers,
        name="Fictional Meridian Industrial Holdings LLC",
        registration="MERIDIAN-002",
        website="https://www.meridian.example/about",
    )
    assert original["duplicate_status"] == "clear"
    assert possible_duplicate["duplicate_status"] == "review_required"

    candidates = client.get(
        "/api/counterparty-duplicates?status=pending", headers=auth_headers
    )
    assert candidates.status_code == 200, candidates.text
    candidate = next(
        item
        for item in candidates.json()
        if item["possible_duplicate_id"] == possible_duplicate["id"]
        and item["existing_counterparty_id"] == original["id"]
    )
    assert float(candidate["name_similarity"]) == 100.0
    signals = json.loads(candidate["signals_json"])
    assert "NAME_EXACT" in signals
    assert "SAME_JURISDICTION" in signals
    assert "SAME_WEBSITE_DOMAIN" in signals

    data_quality = client.post(
        "/api/data-quality/scans", headers=auth_headers, json={}
    )
    assert data_quality.status_code == 201, data_quality.text
    duplicate_issues = client.get(
        "/api/data-quality/issues?code=DQ_COUNTERPARTY_DUPLICATE_REVIEW",
        headers=auth_headers,
    )
    assert any(
        item["entity_id"] == possible_duplicate["id"]
        and item["status"] == "open"
        for item in duplicate_issues.json()
    )

    screening = client.post(
        "/api/counterparties/{}/screen".format(possible_duplicate["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    transaction = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-DUPLICATE-REVIEW",
            "product_description": "Fictional industrial components",
            "origin_country": "SG",
            "destination_country": "US",
            "amount": "25000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "payment_terms_days": 15,
            "deposit_percentage": "30.00",
            "requested_credit_exposure": "15000.00",
            "end_use": "Installation in fictional commercial equipment",
            "parties": [
                {
                    "role": "seller",
                    "name": possible_duplicate["legal_name"],
                    "counterparty_id": possible_duplicate["id"],
                    "country": "SG",
                    "registration_number": possible_duplicate["registration_number"],
                },
                {"role": "end_user", "name": "Fictional Buyer", "country": "US"},
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    assessment = client.post(
        "/api/transactions/{}/assessments".format(transaction.json()["id"]),
        headers=auth_headers,
    )
    assert assessment.status_code == 201, assessment.text
    assessment_data = assessment.json()
    assert assessment_data["recommendation"] == "REFER"
    assert "COUNTERPARTY_DUPLICATE_REVIEW" in json.loads(
        assessment_data["decision"]["reason_codes_json"]
    )
    risk_dimensions = json.loads(assessment_data["decision"]["risk_dimensions_json"])
    assert risk_dimensions["identity_kyb"] == "duplicate_review"

    stale = client.post(
        "/api/counterparty-duplicates/{}/resolve".format(candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "not_duplicate",
            "rationale": "The version is deliberately stale for concurrency testing.",
            "expected_version": 99,
        },
    )
    assert stale.status_code == 409
    resolution = client.post(
        "/api/counterparty-duplicates/{}/resolve".format(candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "not_duplicate",
            "rationale": "Registration evidence confirms two separately incorporated companies.",
            "expected_version": 1,
        },
    )
    assert resolution.status_code == 200, resolution.text
    assert resolution.json()["status"] == "not_duplicate"
    refreshed = client.get(
        "/api/counterparties/{}".format(possible_duplicate["id"]),
        headers=auth_headers,
    )
    assert refreshed.json()["duplicate_status"] == "clear"

    closing_scan = client.post(
        "/api/data-quality/scans", headers=auth_headers, json={}
    )
    assert closing_scan.status_code == 201, closing_scan.text
    resolved_issues = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_COUNTERPARTY_DUPLICATE_REVIEW",
        headers=auth_headers,
    )
    assert any(
        item["entity_id"] == possible_duplicate["id"]
        for item in resolved_issues.json()
    )


def test_alias_match_can_be_confirmed_as_duplicate(client, auth_headers):
    original = _create_counterparty(
        client,
        auth_headers,
        name="Fictional Atlas Export Services Limited",
        registration="ATLAS-001",
        website="https://atlas-one.example",
    )
    possible_duplicate = _create_counterparty(
        client,
        auth_headers,
        name="Fictional AES Trading",
        registration="ATLAS-002",
        website="https://atlas-two.example",
        aliases=[
            {
                "name": "Fictional Atlas Export Services",
                "alias_type": "previous_name",
            }
        ],
    )
    candidates = client.get(
        "/api/counterparty-duplicates?status=pending", headers=auth_headers
    ).json()
    candidate = next(
        item
        for item in candidates
        if item["possible_duplicate_id"] == possible_duplicate["id"]
        and item["existing_counterparty_id"] == original["id"]
    )
    confirmed = client.post(
        "/api/counterparty-duplicates/{}/resolve".format(candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "confirmed_duplicate",
            "rationale": "Registration evidence shows the alias belongs to the canonical entity.",
            "expected_version": 1,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    refreshed = client.get(
        "/api/counterparties/{}".format(possible_duplicate["id"]),
        headers=auth_headers,
    ).json()
    assert refreshed["duplicate_status"] == "confirmed_duplicate"
    assert refreshed["canonical_counterparty_id"] == original["id"]

    frontend = client.get("/")
    assert "Duplicate review" in frontend.text
    assert "PENDING ENTITY MATCHES" in frontend.text
    javascript = client.get("/static/app.js")
    assert "/counterparty-duplicates?limit=200" in javascript.text
    assert "resolveDuplicate" in javascript.text
