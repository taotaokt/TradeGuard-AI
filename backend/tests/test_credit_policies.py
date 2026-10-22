import json
from datetime import datetime
from decimal import Decimal

from backend.app.db import SessionLocal
from backend.app.models import CounterpartyCreditPolicy


def _create_policy_counterparty(client, auth_headers):
    response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Fictional Credit Policy Exporters Ltd",
            "jurisdiction": "GB",
            "registration_number": "CREDIT-POLICY-001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_policy_transaction(
    client,
    auth_headers,
    counterparty,
    *,
    reference,
    amount,
    payment_terms_days,
    deposit_percentage,
):
    response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": reference,
            "product_description": "Fictional trade-credit policy test goods",
            "origin_country": "GB",
            "destination_country": "US",
            "amount": amount,
            "currency": "USD",
            "payment_method": "open_account",
            "payment_terms_days": payment_terms_days,
            "deposit_percentage": deposit_percentage,
            "end_use": "Installation in fictional commercial distribution equipment",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "GB",
                    "registration_number": counterparty["registration_number"],
                },
                {"role": "end_user", "name": "Fictional Policy Buyer", "country": "US"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_policy(client, auth_headers, counterparty_id, **overrides):
    payload = {
        "currency": "usd",
        "risk_tier": "moderate",
        "credit_limit": "50000.00",
        "max_payment_terms_days": 30,
        "minimum_deposit_percentage": "20.00",
        "rationale": "Fictional policy based on the documented internal review.",
        "expires_at": "2030-12-31T00:00:00Z",
    }
    payload.update(overrides)
    response = client.post(
        "/api/counterparties/{}/credit-policies".format(counterparty_id),
        headers=auth_headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_credit_policy_versioning_assessment_controls_and_quality(client, auth_headers):
    counterparty = _create_policy_counterparty(client, auth_headers)
    invalid = client.post(
        "/api/counterparties/{}/credit-policies".format(counterparty["id"]),
        headers=auth_headers,
        json={
            "currency": "USD",
            "risk_tier": "moderate",
            "credit_limit": "1000.00",
            "max_payment_terms_days": 30,
            "minimum_deposit_percentage": "20.00",
            "rationale": "The dates are deliberately invalid for this policy.",
            "effective_from": "2030-01-02T00:00:00Z",
            "expires_at": "2030-01-01T00:00:00Z",
        },
    )
    assert invalid.status_code == 422

    first = _create_policy(client, auth_headers, counterparty["id"])
    assert first["currency"] == "USD"
    assert first["policy_version"] == 1
    assert first["status"] == "draft"

    stale = client.post(
        "/api/credit-policies/{}/actions".format(first["id"]),
        headers=auth_headers,
        json={
            "action": "activate",
            "rationale": "Deliberately stale policy version for concurrency testing.",
            "expected_record_version": 99,
        },
    )
    assert stale.status_code == 409
    activated = client.post(
        "/api/credit-policies/{}/actions".format(first["id"]),
        headers=auth_headers,
        json={
            "action": "activate",
            "rationale": "Risk review approves this fictional initial customer limit.",
            "expected_record_version": 1,
        },
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["record_version"] == 2

    existing = _create_policy_transaction(
        client,
        auth_headers,
        counterparty,
        reference="POLICY-EXISTING-001",
        amount="30000.00",
        payment_terms_days=20,
        deposit_percentage="20.00",
    )
    assert existing["status"] == "draft"
    proposed = _create_policy_transaction(
        client,
        auth_headers,
        counterparty,
        reference="POLICY-BREACH-001",
        amount="40000.00",
        payment_terms_days=60,
        deposit_percentage="10.00",
    )
    assessment = client.post(
        "/api/transactions/{}/assessments".format(proposed["id"]),
        headers=auth_headers,
    )
    assert assessment.status_code == 201, assessment.text
    assessment_data = assessment.json()
    reason_codes = {item["reason_code"] for item in assessment_data["rule_results"]}
    assert {
        "CREDIT_LIMIT_EXCEEDED",
        "PAYMENT_TERMS_EXCEED_POLICY",
        "DEPOSIT_BELOW_POLICY",
    }.issubset(reason_codes)
    assert assessment_data["recommendation"] == "REFER"
    dimensions = json.loads(assessment_data["decision"]["risk_dimensions_json"])
    assert dimensions["counterparty_credit_policy"] == "breached"
    snapshot = json.loads(assessment_data["screening_snapshot_json"])
    policy_snapshot = snapshot["credit_policy_state"]["policies"][0]
    assert policy_snapshot["id"] == first["id"]
    assert Decimal(policy_snapshot["current_exposure"]) == Decimal("24000.00")
    assert Decimal(policy_snapshot["proposed_exposure"]) == Decimal("36000.00")
    assert Decimal(policy_snapshot["projected_exposure"]) == Decimal("60000.00")
    assert Decimal(policy_snapshot["credit_limit"]) == Decimal("50000.00")

    second = _create_policy(
        client,
        auth_headers,
        counterparty["id"],
        risk_tier="low",
        credit_limit="100000.00",
        max_payment_terms_days=90,
        minimum_deposit_percentage="5.00",
        rationale="Expanded fictional policy after a documented risk review.",
    )
    assert second["policy_version"] == 2
    second_activation = client.post(
        "/api/credit-policies/{}/actions".format(second["id"]),
        headers=auth_headers,
        json={
            "action": "activate",
            "rationale": "Risk review approves the replacement fictional policy.",
            "expected_record_version": 1,
        },
    )
    assert second_activation.status_code == 200, second_activation.text
    policies = client.get(
        "/api/counterparties/{}/credit-policies".format(counterparty["id"]),
        headers=auth_headers,
    )
    assert policies.status_code == 200, policies.text
    by_id = {item["id"]: item for item in policies.json()}
    assert by_id[first["id"]]["status"] == "retired"
    assert by_id[first["id"]]["record_version"] == 3
    assert by_id[second["id"]]["status"] == "active"

    with SessionLocal() as db:
        stored = db.get(CounterpartyCreditPolicy, second["id"])
        stored.expires_at = datetime(2020, 1, 1)
        db.commit()
    quality_scan = client.post("/api/data-quality/scans", headers=auth_headers, json={})
    assert quality_scan.status_code == 201, quality_scan.text
    expired_issues = client.get(
        "/api/data-quality/issues?status=open&code=DQ_CREDIT_POLICY_EXPIRED",
        headers=auth_headers,
    ).json()
    assert second["id"] in {item["entity_id"] for item in expired_issues}

    retired = client.post(
        "/api/credit-policies/{}/actions".format(second["id"]),
        headers=auth_headers,
        json={
            "action": "retire",
            "rationale": "The expired fictional policy requires a replacement review.",
            "expected_record_version": 2,
        },
    )
    assert retired.status_code == 200, retired.text
    closing_scan = client.post("/api/data-quality/scans", headers=auth_headers, json={})
    assert closing_scan.status_code == 201, closing_scan.text
    resolved = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_CREDIT_POLICY_EXPIRED",
        headers=auth_headers,
    ).json()
    assert second["id"] in {item["entity_id"] for item in resolved}

    restricted_policy = _create_policy(
        client,
        auth_headers,
        counterparty["id"],
        risk_tier="restricted",
        credit_limit="1000000.00",
        max_payment_terms_days=365,
        minimum_deposit_percentage="0.00",
        rationale="New exposure is paused by this fictional restricted policy.",
    )
    restricted_activation = client.post(
        "/api/credit-policies/{}/actions".format(restricted_policy["id"]),
        headers=auth_headers,
        json={
            "action": "activate",
            "rationale": "Risk review activates a documented restriction on new exposure.",
            "expected_record_version": 1,
        },
    )
    assert restricted_activation.status_code == 200, restricted_activation.text
    stopped_transaction = _create_policy_transaction(
        client,
        auth_headers,
        counterparty,
        reference="POLICY-RESTRICTED-001",
        amount="1000.00",
        payment_terms_days=0,
        deposit_percentage="100.00",
    )
    stopped_assessment = client.post(
        "/api/transactions/{}/assessments".format(stopped_transaction["id"]),
        headers=auth_headers,
    )
    assert stopped_assessment.status_code == 201, stopped_assessment.text
    assert stopped_assessment.json()["recommendation"] == "STOP"
    assert stopped_assessment.json()["decision"]["hard_stop"] is True
    assert "COUNTERPARTY_CREDIT_RESTRICTED" in {
        item["reason_code"] for item in stopped_assessment.json()["rule_results"]
    }
    confirmed_stop = client.post(
        "/api/assessments/{}/reviews".format(stopped_assessment.json()["id"]),
        headers=auth_headers,
        json={
            "decision": "STOP",
            "rationale": "Risk review confirms the active restricted-credit policy hard stop.",
        },
    )
    assert confirmed_stop.status_code == 200, confirmed_stop.text
    assert confirmed_stop.json()["status"] == "stopped"
    assert confirmed_stop.json()["review_case"]["status"] == "stopped_by_policy"

    audit_actions = {
        item["action"]
        for item in client.get("/api/audit-events?limit=200", headers=auth_headers).json()
        if item["object_id"] in {first["id"], second["id"], restricted_policy["id"]}
    }
    assert {
        "credit_policy.created",
        "credit_policy.activate",
        "credit_policy.retire",
    }.issubset(audit_actions)


def test_credit_policy_frontend_workspace(client):
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "Credit policies" in frontend.text
    assert "NEW POLICY VERSION" in frontend.text
    javascript = client.get("/static/app.js")
    assert "/credit-policies" in javascript.text
    assert "actOnCreditPolicy" in javascript.text
