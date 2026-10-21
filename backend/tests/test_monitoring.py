from backend.app.db import SessionLocal
from backend.app.models import User
from backend.app.security import hash_password


def _create_monitoring_fixture(client, auth_headers):
    source = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "monitoring-alert-list",
            "name": "Fictional Monitoring Alert List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/monitoring-list",
        },
    )
    assert source.status_code == 201, source.text
    csv_content = (
        "source_id,name,entity_type,country,program,remarks\n"
        "MON-001,Monitoring Restricted Widgets,entity,DE,DEMO PROGRAM,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "monitoring-v1", "effective_at": "2026-10-21"},
        files={"file": ("monitoring-list.csv", csv_content, "text/csv")},
    )
    assert version.status_code == 201, version.text
    activated = client.post(
        "/api/screening/versions/{}/activate".format(version.json()["id"]),
        headers=auth_headers,
    )
    assert activated.status_code == 200, activated.text

    counterparty = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Monitoring Restricted Widgets",
            "jurisdiction": "DE",
            "registration_number": "MONITOR-001",
        },
    )
    assert counterparty.status_code == 201, counterparty.text
    counterparty_data = counterparty.json()
    transaction = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-MONITORING-001",
            "product_description": "Commercial packaging equipment",
            "origin_country": "DE",
            "destination_country": "US",
            "amount": "24000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "payment_terms_days": 15,
            "deposit_percentage": "30.00",
            "requested_credit_exposure": "16800.00",
            "end_use": "Packaging consumer goods for retail distribution",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty_data["legal_name"],
                    "counterparty_id": counterparty_data["id"],
                    "country": "DE",
                    "registration_number": counterparty_data["registration_number"],
                },
                {
                    "role": "end_user",
                    "name": "Fictional Retail Packing Company",
                    "country": "US",
                },
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    return counterparty_data, transaction.json()


def test_screening_alert_lifecycle_and_reassessment(client, auth_headers):
    counterparty, transaction = _create_monitoring_fixture(client, auth_headers)
    initial = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]),
        headers=auth_headers,
    )
    assert initial.status_code == 201, initial.text
    assert initial.json()["version"] == 1

    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    assert screening.json()["candidates"]

    listed = client.get(
        "/api/alerts?counterparty_id={}".format(counterparty["id"]), headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    alerts = listed.json()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["alert_type"] == "screening_match"
    assert alert["severity"] == "high"
    assert alert["required_role"] == "compliance_reviewer"
    assert alert["status"] == "open"
    assert alert["screening_run_id"] == screening.json()["id"]
    assert transaction["id"] in alert["source_reference_json"]

    with SessionLocal() as db:
        risk_user = User(
            email="monitoring-risk@example.test",
            full_name="Monitoring Risk Reviewer",
            password_hash=hash_password("test-password"),
            role="risk_reviewer",
        )
        db.add(risk_user)
        db.commit()
    risk_login = client.post(
        "/api/auth/login",
        json={"email": "monitoring-risk@example.test", "password": "test-password"},
    )
    risk_headers = {"Authorization": "Bearer {}".format(risk_login.json()["access_token"])}
    wrong_role = client.post(
        "/api/alerts/{}/actions".format(alert["id"]),
        headers=risk_headers,
        json={
            "action": "acknowledge",
            "rationale": "Risk reviewers cannot clear compliance-owned alerts.",
        },
    )
    assert wrong_role.status_code == 403

    me = client.get("/api/auth/me", headers=auth_headers).json()
    assigned = client.post(
        "/api/alerts/{}/actions".format(alert["id"]),
        headers=auth_headers,
        json={
            "action": "assign",
            "assignee_id": me["id"],
            "rationale": "Administrator owns the monitoring review.",
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_id"] == me["id"]

    acknowledged = client.post(
        "/api/alerts/{}/actions".format(alert["id"]),
        headers=auth_headers,
        json={
            "action": "acknowledge",
            "rationale": "Candidate evidence is being reviewed before reassessment.",
        },
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["acknowledged_by_id"] == me["id"]

    reassessment = client.post(
        "/api/alerts/{}/reassess".format(alert["id"]),
        headers=auth_headers,
        json={
            "transaction_id": transaction["id"],
            "rationale": "Reassess the open exposure against the new screening result.",
        },
    )
    assert reassessment.status_code == 200, reassessment.text
    assert reassessment.json()["version"] == 2
    assert reassessment.json()["transaction_id"] == transaction["id"]

    closed = client.get(
        "/api/alerts?status=resolved&counterparty_id={}".format(counterparty["id"]),
        headers=auth_headers,
    )
    assert closed.status_code == 200, closed.text
    resolved_alert = closed.json()[0]
    assert resolved_alert["transaction_id"] == transaction["id"]
    assert resolved_alert["reassessment_id"] == reassessment.json()["id"]
    assert resolved_alert["resolved_by_id"] == me["id"]

    repeated_action = client.post(
        "/api/alerts/{}/actions".format(alert["id"]),
        headers=auth_headers,
        json={"action": "dismiss", "rationale": "Closed alerts cannot be dismissed again."},
    )
    assert repeated_action.status_code == 409

    dashboard = client.get("/api/dashboard/summary", headers=auth_headers)
    assert dashboard.status_code == 200
    assert isinstance(dashboard.json()["open_alerts"], int)

    audit = client.get("/api/audit-events?limit=500", headers=auth_headers)
    actions = {item["action"] for item in audit.json()}
    assert {
        "alert.created",
        "alert.assigned",
        "alert.acknowledged",
        "alert.reassessment_created",
        "assessment.submitted_from_alert",
    }.issubset(actions)
