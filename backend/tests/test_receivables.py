import json
from decimal import Decimal


def _create_counterparty(client, auth_headers, suffix):
    response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Fictional Receivables Buyer {}".format(suffix),
            "jurisdiction": "US",
            "registration_number": "AR-{}".format(suffix),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_transaction(client, auth_headers, counterparty, reference, amount):
    response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": reference,
            "product_description": "Fictional industrial components for receivables testing",
            "origin_country": "CN",
            "destination_country": "US",
            "amount": amount,
            "currency": "USD",
            "payment_method": "open_account",
            "payment_terms_days": 30,
            "deposit_percentage": "0.00",
            "end_use": "Installation in fictional commercial production equipment",
            "parties": [
                {
                    "role": "buyer",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "US",
                    "registration_number": counterparty["registration_number"],
                },
                {"role": "end_user", "name": "Fictional Factory", "country": "US"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _activate_credit_policy(client, auth_headers, counterparty_id):
    created = client.post(
        "/api/counterparties/{}/credit-policies".format(counterparty_id),
        headers=auth_headers,
        json={
            "currency": "USD",
            "risk_tier": "moderate",
            "credit_limit": "10000.00",
            "max_payment_terms_days": 60,
            "minimum_deposit_percentage": "0.00",
            "rationale": "Fictional receivables-aware credit limit test.",
            "expires_at": "2030-12-31T00:00:00Z",
        },
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    activated = client.post(
        "/api/credit-policies/{}/actions".format(policy["id"]),
        headers=auth_headers,
        json={
            "action": "activate",
            "rationale": "Approve the fictional limit for the receivables test.",
            "expected_record_version": 1,
        },
    )
    assert activated.status_code == 200, activated.text
    return activated.json()


def test_receivable_payment_lifecycle_exposure_quality_and_outcome(client, auth_headers):
    counterparty = _create_counterparty(client, auth_headers, "001")
    other_counterparty = _create_counterparty(client, auth_headers, "002")
    _activate_credit_policy(client, auth_headers, counterparty["id"])
    transaction = _create_transaction(
        client, auth_headers, counterparty, "AR-TRANSACTION-001", "10000.00"
    )

    wrong_party = client.post(
        "/api/transactions/{}/receivable".format(transaction["id"]),
        headers=auth_headers,
        json={
            "counterparty_id": other_counterparty["id"],
            "invoice_reference": "AR-INVOICE-WRONG",
            "invoice_amount": "10000.00",
            "issued_at": "2025-01-01T00:00:00Z",
            "due_at": "2025-01-31T00:00:00Z",
        },
    )
    assert wrong_party.status_code == 422

    opened = client.post(
        "/api/transactions/{}/receivable".format(transaction["id"]),
        headers=auth_headers,
        json={
            "counterparty_id": counterparty["id"],
            "invoice_reference": "AR-INVOICE-001",
            "invoice_amount": "10000.00",
            "issued_at": "2025-01-01T00:00:00Z",
            "due_at": "2025-01-31T00:00:00Z",
            "notes": "Fictional overdue invoice for lifecycle testing.",
        },
    )
    assert opened.status_code == 201, opened.text
    receivable = opened.json()
    assert receivable["status"] == "open"
    assert receivable["aging_status"] == "overdue"
    assert receivable["days_past_due"] > 0
    assert Decimal(receivable["outstanding_amount"]) == Decimal("10000.00")

    duplicate = client.post(
        "/api/transactions/{}/receivable".format(transaction["id"]),
        headers=auth_headers,
        json={
            "counterparty_id": counterparty["id"],
            "invoice_reference": "AR-INVOICE-002",
            "invoice_amount": "1000.00",
            "issued_at": "2025-01-01T00:00:00Z",
            "due_at": "2025-01-31T00:00:00Z",
        },
    )
    assert duplicate.status_code == 409

    scan = client.post("/api/data-quality/scans", headers=auth_headers, json={})
    assert scan.status_code == 201, scan.text
    overdue_issues = client.get(
        "/api/data-quality/issues?status=open&code=DQ_RECEIVABLE_OVERDUE",
        headers=auth_headers,
    ).json()
    assert receivable["id"] in {item["entity_id"] for item in overdue_issues}

    partial = client.post(
        "/api/receivables/{}/payments".format(receivable["id"]),
        headers=auth_headers,
        json={
            "payment_reference": "AR-PAYMENT-001",
            "amount": "4000.00",
            "received_at": "2025-02-10T00:00:00Z",
            "expected_version": 1,
        },
    )
    assert partial.status_code == 200, partial.text
    partial_data = partial.json()
    assert partial_data["status"] == "partially_paid"
    assert partial_data["version"] == 2
    assert Decimal(partial_data["outstanding_amount"]) == Decimal("6000.00")
    assert len(partial_data["payments"]) == 1

    stale = client.post(
        "/api/receivables/{}/payments".format(receivable["id"]),
        headers=auth_headers,
        json={
            "payment_reference": "AR-PAYMENT-STALE",
            "amount": "100.00",
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409
    repeated_reference = client.post(
        "/api/receivables/{}/payments".format(receivable["id"]),
        headers=auth_headers,
        json={
            "payment_reference": "AR-PAYMENT-001",
            "amount": "100.00",
            "expected_version": 2,
        },
    )
    assert repeated_reference.status_code == 409
    overpayment = client.post(
        "/api/receivables/{}/payments".format(receivable["id"]),
        headers=auth_headers,
        json={
            "payment_reference": "AR-PAYMENT-OVER",
            "amount": "6000.01",
            "expected_version": 2,
        },
    )
    assert overpayment.status_code == 422

    proposed = _create_transaction(
        client, auth_headers, counterparty, "AR-TRANSACTION-002", "5000.00"
    )
    assessment = client.post(
        "/api/transactions/{}/assessments".format(proposed["id"]), headers=auth_headers
    )
    assert assessment.status_code == 201, assessment.text
    assessment_data = assessment.json()
    assert "CREDIT_LIMIT_EXCEEDED" in {
        result["reason_code"] for result in assessment_data["rule_results"]
    }
    policy = json.loads(assessment_data["screening_snapshot_json"])[
        "credit_policy_state"
    ]["policies"][0]
    assert Decimal(policy["receivable_exposure"]) == Decimal("6000.00")
    assert Decimal(policy["estimated_uninvoiced_exposure"]) == Decimal("0.00")
    assert Decimal(policy["current_exposure"]) == Decimal("6000.00")
    assert Decimal(policy["projected_exposure"]) == Decimal("11000.00")

    settled = client.post(
        "/api/receivables/{}/payments".format(receivable["id"]),
        headers=auth_headers,
        json={
            "payment_reference": "AR-PAYMENT-002",
            "amount": "6000.00",
            "received_at": "2026-02-15T00:00:00Z",
            "expected_version": 2,
        },
    )
    assert settled.status_code == 200, settled.text
    settled_data = settled.json()
    assert settled_data["status"] == "paid"
    assert settled_data["aging_status"] == "paid"
    assert settled_data["version"] == 3
    assert Decimal(settled_data["outstanding_amount"]) == Decimal("0.00")

    outcome = client.get(
        "/api/transactions/{}/outcome".format(transaction["id"]), headers=auth_headers
    )
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["outcome_type"] == "delayed"
    assert outcome.json()["days_past_due"] >= 30
    alerts = client.get(
        "/api/alerts?transaction_id={}".format(transaction["id"]), headers=auth_headers
    )
    assert alerts.status_code == 200, alerts.text
    assert any(item["alert_type"] == "adverse_payment_outcome" for item in alerts.json())

    closed_scan = client.post("/api/data-quality/scans", headers=auth_headers, json={})
    assert closed_scan.status_code == 201, closed_scan.text
    resolved = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_RECEIVABLE_OVERDUE",
        headers=auth_headers,
    ).json()
    assert receivable["id"] in {item["entity_id"] for item in resolved}

    audit = client.get("/api/audit-events?limit=200", headers=auth_headers)
    assert audit.status_code == 200, audit.text
    actions = {item["action"] for item in audit.json()}
    assert {"receivable.created", "receivable.payment_recorded"}.issubset(actions)


def test_receivables_frontend_is_exposed(client):
    page = client.get("/")
    javascript = client.get("/static/app.js")
    assert page.status_code == 200
    assert 'data-view="receivables"' in page.text
    assert 'id="receivable-form"' in page.text
    assert javascript.status_code == 200
    assert 'api("/receivables?limit=200")' in javascript.text
    assert "/payments" in javascript.text
