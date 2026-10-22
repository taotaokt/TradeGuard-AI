from io import BytesIO

from pypdf import PdfReader

from backend.tests.test_api import (
    _create_clean_screened_counterparty,
    _create_decision_transaction,
)


def test_approval_conditions_require_evidence_and_feed_data_quality(client, auth_headers):
    counterparty = _create_clean_screened_counterparty(
        client, auth_headers, "condition-lifecycle"
    )
    transaction = _create_decision_transaction(
        client,
        auth_headers,
        reference="PO-CONDITION-LIFECYCLE",
        counterparty=counterparty,
        payment_terms_days=60,
    )
    assessment_response = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]),
        headers=auth_headers,
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()
    assert assessment["recommendation"] == "REFER"

    review = client.post(
        "/api/assessments/{}/reviews".format(assessment["id"]),
        headers=auth_headers,
        json={
            "decision": "APPROVE_WITH_CONDITIONS",
            "rationale": "The transaction can proceed after documented controls are completed.",
            "conditions": [
                "Obtain an irrevocable letter of credit before shipment",
                "Confirm the final consignee before releasing the goods",
            ],
            "condition_due_days": 0,
            "condition_owner_role": "risk_reviewer",
        },
    )
    assert review.status_code == 200, review.text
    structured = review.json()["decision"]["conditions"]
    assert len(structured) == 2
    assert all(item["status"] == "open" for item in structured)
    assert all(item["owner_role"] == "risk_reviewer" for item in structured)

    listed = client.get(
        "/api/conditions?assessment_id={}".format(assessment["id"]),
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    conditions = listed.json()
    assert [item["sequence"] for item in conditions] == [1, 2]

    data_quality = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={
            "screening_stale_days": 30,
            "list_stale_days": 30,
            "outcome_grace_days": 30,
        },
    )
    assert data_quality.status_code == 201, data_quality.text
    issues = client.get(
        "/api/data-quality/issues?code=DQ_DECISION_CONDITION_OVERDUE",
        headers=auth_headers,
    )
    condition_ids = {item["id"] for item in conditions}
    assert {
        item["entity_id"] for item in issues.json() if item["status"] == "open"
    }.issuperset(condition_ids)

    no_evidence = client.post(
        "/api/conditions/{}/actions".format(conditions[0]["id"]),
        headers=auth_headers,
        json={
            "action": "fulfill",
            "rationale": "The required payment control has been received.",
            "expected_version": 1,
        },
    )
    assert no_evidence.status_code == 422

    document = client.post(
        "/api/transactions/{}/documents".format(transaction["id"]),
        headers=auth_headers,
        data={"document_type": "contract"},
        files={
            "file": (
                "condition-evidence.pdf",
                b"%PDF-1.4 fictional condition evidence",
                "application/pdf",
            )
        },
    )
    assert document.status_code == 201, document.text
    fulfilled = client.post(
        "/api/conditions/{}/actions".format(conditions[0]["id"]),
        headers=auth_headers,
        json={
            "action": "fulfill",
            "rationale": "The payment control is supported by the attached contract.",
            "expected_version": 1,
            "evidence_document_id": document.json()["id"],
        },
    )
    assert fulfilled.status_code == 200, fulfilled.text
    assert fulfilled.json()["status"] == "fulfilled"
    assert fulfilled.json()["version"] == 2

    stale_action = client.post(
        "/api/conditions/{}/actions".format(conditions[0]["id"]),
        headers=auth_headers,
        json={
            "action": "reopen",
            "rationale": "This uses a stale condition version and must fail.",
            "expected_version": 1,
        },
    )
    assert stale_action.status_code == 409

    waived = client.post(
        "/api/conditions/{}/actions".format(conditions[1]["id"]),
        headers=auth_headers,
        json={
            "action": "waive",
            "rationale": "The consignee was independently confirmed in the final contract.",
            "expected_version": 1,
        },
    )
    assert waived.status_code == 200, waived.text
    assert waived.json()["status"] == "waived"

    report = client.get(
        "/api/assessments/{}/report".format(assessment["id"]), headers=auth_headers
    )
    assert report.status_code == 200, report.text
    report_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(report.content)).pages
    )
    assert "Status: Fulfilled" in report_text
    assert "Status: Waived" in report_text
    assert document.json()["id"] in report_text

    closing_scan = client.post(
        "/api/data-quality/scans",
        headers=auth_headers,
        json={
            "screening_stale_days": 30,
            "list_stale_days": 30,
            "outcome_grace_days": 30,
        },
    )
    assert closing_scan.status_code == 201, closing_scan.text
    resolved = client.get(
        "/api/data-quality/issues?status=resolved&code=DQ_DECISION_CONDITION_OVERDUE",
        headers=auth_headers,
    )
    assert {
        item["entity_id"] for item in resolved.json()
    }.issuperset(condition_ids)

    audit = client.get("/api/audit-events?limit=200", headers=auth_headers)
    actions = {item["action"] for item in audit.json()}
    assert "decision_condition.fulfill" in actions
    assert "decision_condition.waive" in actions


def test_condition_payload_rejects_empty_text(client, auth_headers):
    response = client.post(
        "/api/assessments/not-a-real-assessment/reviews",
        headers=auth_headers,
        json={
            "decision": "APPROVE_WITH_CONDITIONS",
            "rationale": "This payload should fail before assessment lookup occurs.",
            "conditions": ["   "],
        },
    )
    assert response.status_code == 422

    frontend = client.get("/")
    assert "CONDITION REGISTER" in frontend.text
    javascript = client.get("/static/app.js")
    assert "/conditions?limit=200" in javascript.text
    assert "actOnCondition" in javascript.text
