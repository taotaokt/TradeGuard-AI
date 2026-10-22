import json


def _create_data_quality_fixture(client, auth_headers):
    screening_list = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "dq-old-list",
            "name": "Fictional Old Data Quality List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/dq-old-list",
        },
    )
    assert screening_list.status_code == 201, screening_list.text
    version = client.post(
        "/api/screening/lists/{}/versions/import".format(screening_list.json()["id"]),
        headers=auth_headers,
        data={"version": "dq-old-v1", "effective_at": "2020-01-01"},
        files={
            "file": (
                "dq-list.csv",
                b"source_id,name,entity_type,country\nDQ-1,Fictional DQ Entity,entity,GB\n",
                "text/csv",
            )
        },
    )
    assert version.status_code == 201, version.text
    activation = client.post(
        "/api/screening/versions/{}/activate".format(version.json()["id"]),
        headers=auth_headers,
    )
    assert activation.status_code == 200, activation.text

    counterparty = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Fictional Data Quality Imports Ltd",
            "jurisdiction": "SG",
            "registration_number": "DQ-CP-001",
        },
    )
    assert counterparty.status_code == 201, counterparty.text
    counterparty_data = counterparty.json()
    transaction = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "DQ-TX-001",
            "product_description": "Fictional test components",
            "origin_country": "SG",
            "destination_country": "US",
            "amount": "1000.00",
            "currency": "USD",
            "payment_method": "open_account",
            "payment_terms_days": 0,
            "deposit_percentage": "0.00",
            "parties": [
                {
                    "role": "counterparty",
                    "name": counterparty_data["legal_name"],
                    "counterparty_id": counterparty_data["id"],
                    "country": counterparty_data["jurisdiction"],
                    "registration_number": counterparty_data["registration_number"],
                }
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    return screening_list.json()["id"], counterparty_data, transaction.json()


def test_data_quality_scan_deduplicates_and_auto_resolves(client, auth_headers):
    list_id, counterparty, transaction = _create_data_quality_fixture(client, auth_headers)
    scan_payload = {
        "screening_stale_days": 1,
        "list_stale_days": 1,
        "outcome_grace_days": 0,
    }
    first_scan = client.post(
        "/api/data-quality/scans", headers=auth_headers, json=scan_payload
    )
    assert first_scan.status_code == 201, first_scan.text
    counters = json.loads(first_scan.json()["counters_json"])
    assert counters["findings"] >= 6
    assert counters["new"] >= 6

    issues = client.get("/api/data-quality/issues", headers=auth_headers)
    assert issues.status_code == 200, issues.text
    relevant_entity_ids = {counterparty["id"], transaction["id"], list_id}
    relevant = [item for item in issues.json() if item["entity_id"] in relevant_entity_ids]
    codes = {item["code"] for item in relevant}
    assert {
        "DQ_COUNTERPARTY_NO_EVIDENCE",
        "DQ_COUNTERPARTY_NEVER_SCREENED",
        "DQ_SCREENING_LIST_STALE",
        "DQ_TRANSACTION_MISSING_END_USE",
        "DQ_TRANSACTION_NO_EVIDENCE",
        "DQ_TRANSACTION_OUTCOME_OVERDUE",
    }.issubset(codes)
    issue_ids = {item["issue_key"]: item["id"] for item in relevant}

    second_scan = client.post(
        "/api/data-quality/scans", headers=auth_headers, json=scan_payload
    )
    assert second_scan.status_code == 201, second_scan.text
    second_counters = json.loads(second_scan.json()["counters_json"])
    assert second_counters["recurring"] >= 6
    second_issues = client.get("/api/data-quality/issues", headers=auth_headers).json()
    assert {
        item["issue_key"]: item["id"]
        for item in second_issues
        if item["entity_id"] in relevant_entity_ids
    } == issue_ids

    evidence = client.post(
        "/api/counterparties/{}/evidence".format(counterparty["id"]),
        headers=auth_headers,
        data={"document_type": "business_registration"},
        files={"file": ("registration.pdf", b"%PDF-1.4 fictional", "application/pdf")},
    )
    assert evidence.status_code == 201, evidence.text
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    outcome = client.post(
        "/api/transactions/{}/outcome".format(transaction["id"]),
        headers=auth_headers,
        json={"outcome_type": "cancelled", "days_past_due": 0},
    )
    assert outcome.status_code == 201, outcome.text

    third_scan = client.post(
        "/api/data-quality/scans", headers=auth_headers, json=scan_payload
    )
    assert third_scan.status_code == 201, third_scan.text
    third_counters = json.loads(third_scan.json()["counters_json"])
    assert third_counters["auto_resolved"] >= 5
    closed = client.get("/api/data-quality/issues?status=resolved", headers=auth_headers)
    closed_codes = {
        item["code"]
        for item in closed.json()
        if item["entity_id"] in {counterparty["id"], transaction["id"]}
    }
    assert {
        "DQ_COUNTERPARTY_NO_EVIDENCE",
        "DQ_COUNTERPARTY_NEVER_SCREENED",
        "DQ_TRANSACTION_MISSING_END_USE",
        "DQ_TRANSACTION_NO_EVIDENCE",
        "DQ_TRANSACTION_OUTCOME_OVERDUE",
    }.issubset(closed_codes)

    stale_list_issue = next(
        item
        for item in client.get(
            "/api/data-quality/issues?status=open", headers=auth_headers
        ).json()
        if item["entity_id"] == list_id and item["code"] == "DQ_SCREENING_LIST_STALE"
    )
    dismissed = client.post(
        "/api/data-quality/issues/{}/actions".format(stale_list_issue["id"]),
        headers=auth_headers,
        json={
            "action": "dismiss",
            "rationale": "Accepted for the fictional data-quality test only.",
        },
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["status"] == "dismissed"


def test_data_quality_validation_and_frontend(client, auth_headers):
    invalid = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={"screening_stale_days": 0},
    )
    assert invalid.status_code == 422
    frontend = client.get("/")
    assert "Data quality" in frontend.text
    assert "OPEN REMEDIATION ITEMS" in frontend.text
    javascript = client.get("/static/app.js")
    assert "/data-quality/scans" in javascript.text
    assert "actOnDataQualityIssue" in javascript.text
