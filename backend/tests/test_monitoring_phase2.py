import json
from types import SimpleNamespace

from backend.app.drift import calculate_drift_metrics


def _activate_phase2_list(client, auth_headers):
    source = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "phase2-monitoring-list",
            "name": "Fictional Phase 2 Monitoring List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/phase2-list",
        },
    )
    assert source.status_code == 201, source.text
    csv_content = (
        "source_id,name,entity_type,country,program,remarks\n"
        "PHASE2-001,Fictional Unrelated Listed Entity,entity,FR,DEMO,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "phase2-v1", "effective_at": "2026-10-21"},
        files={"file": ("phase2-list.csv", csv_content, "text/csv")},
    )
    assert version.status_code == 201, version.text
    activation = client.post(
        "/api/screening/versions/{}/activate".format(version.json()["id"]),
        headers=auth_headers,
    )
    assert activation.status_code == 200, activation.text


def _create_outcome_transaction(client, auth_headers):
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Phase Two Components GmbH",
            "jurisdiction": "DE",
            "registration_number": "PHASE2-CP-001",
        },
    )
    assert counterparty_response.status_code == 201, counterparty_response.text
    counterparty = counterparty_response.json()
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    assert screening.json()["candidates"] == []

    transaction_response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-PHASE2-OUTCOME-001",
            "product_description": "Commercial refrigeration valves",
            "origin_country": "DE",
            "destination_country": "US",
            "amount": "35000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "payment_terms_days": 15,
            "deposit_percentage": "35.00",
            "requested_credit_exposure": "22750.00",
            "end_use": "Installation in commercial food distribution warehouses",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "DE",
                    "registration_number": counterparty["registration_number"],
                },
                {
                    "role": "end_user",
                    "name": "Fictional Cold Storage Operator",
                    "country": "US",
                },
            ],
        },
    )
    assert transaction_response.status_code == 201, transaction_response.text
    transaction = transaction_response.json()
    assessment = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]),
        headers=auth_headers,
    )
    assert assessment.status_code == 201, assessment.text
    assert assessment.json()["prediction"] is not None
    return counterparty, transaction, assessment.json()


def test_portfolio_rescreen_outcomes_and_drift_snapshot(client, auth_headers):
    _activate_phase2_list(client, auth_headers)
    counterparty, transaction, assessment = _create_outcome_transaction(client, auth_headers)

    unscreened = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Phase Two Unscreened Exporter",
            "jurisdiction": "CA",
            "registration_number": "PHASE2-UNSCREENED-001",
        },
    )
    assert unscreened.status_code == 201, unscreened.text
    monitoring_run = client.post(
        "/api/monitoring/runs/rescreen",
        headers=auth_headers,
        json={"force": False, "fuzzy_threshold": 90},
    )
    assert monitoring_run.status_code == 201, monitoring_run.text
    run_data = monitoring_run.json()
    counters = json.loads(run_data["counters_json"])
    assert run_data["status"] == "completed"
    assert counters["processed"] >= 1
    assert counters["eligible_counterparties"] >= counters["processed"]

    second_run = client.post(
        "/api/monitoring/runs/rescreen",
        headers=auth_headers,
        json={"force": False, "fuzzy_threshold": 90},
    )
    assert second_run.status_code == 201, second_run.text
    second_counters = json.loads(second_run.json()["counters_json"])
    assert second_counters["processed"] == 0
    assert second_counters["skipped_current"] == second_counters["eligible_counterparties"]

    invalid_outcome = client.post(
        "/api/transactions/{}/outcome".format(transaction["id"]),
        headers=auth_headers,
        json={"outcome_type": "paid_on_time", "days_past_due": 1},
    )
    assert invalid_outcome.status_code == 422

    outcome = client.post(
        "/api/transactions/{}/outcome".format(transaction["id"]),
        headers=auth_headers,
        json={
            "assessment_id": assessment["id"],
            "outcome_type": "material_loss",
            "days_past_due": 95,
            "loss_amount": "2500.00",
            "currency": "usd",
            "notes": "Fictional portfolio-monitoring loss event.",
        },
    )
    assert outcome.status_code == 201, outcome.text
    assert outcome.json()["currency"] == "USD"
    assert outcome.json()["assessment_id"] == assessment["id"]

    duplicate = client.post(
        "/api/transactions/{}/outcome".format(transaction["id"]),
        headers=auth_headers,
        json={"outcome_type": "cancelled"},
    )
    assert duplicate.status_code == 409
    saved_outcome = client.get(
        "/api/transactions/{}/outcome".format(transaction["id"]), headers=auth_headers
    )
    assert saved_outcome.status_code == 200
    assert saved_outcome.json()["id"] == outcome.json()["id"]

    alerts = client.get(
        "/api/alerts?counterparty_id={}".format(counterparty["id"]), headers=auth_headers
    )
    adverse_alert = next(
        item for item in alerts.json() if item["alert_type"] == "adverse_payment_outcome"
    )
    assert adverse_alert["severity"] == "critical"
    assert adverse_alert["required_role"] == "risk_reviewer"
    assert adverse_alert["transaction_id"] == transaction["id"]

    drift = client.post(
        "/api/monitoring/drift-snapshots",
        headers=auth_headers,
        json={"window_days": 90, "minimum_sample_size": 5},
    )
    assert drift.status_code == 201, drift.text
    drift_data = drift.json()
    metrics = json.loads(drift_data["metrics_json"])
    assert drift_data["sample_size"] >= 1
    assert drift_data["labeled_count"] >= 1
    assert drift_data["status"] in {"insufficient_data", "stable", "warning", "critical"}
    assert metrics["brier_score"] is not None

    run_history = client.get("/api/monitoring/runs", headers=auth_headers)
    drift_history = client.get("/api/monitoring/drift-snapshots", headers=auth_headers)
    assert run_history.status_code == 200
    assert drift_history.status_code == 200
    assert drift_history.json()[0]["id"] == drift_data["id"]


def test_drift_calculation_detects_material_shift():
    predictions = [
        {
            "transaction_id": "transaction-{}".format(index),
            "probability": 0.8,
            "confidence": "low",
            "risk_band": "critical",
        }
        for index in range(5)
    ]
    outcomes = {
        "transaction-{}".format(index): SimpleNamespace(
            outcome_type="material_loss", days_past_due=120
        )
        for index in range(5)
    }
    status, metrics, thresholds = calculate_drift_metrics(
        predictions,
        outcomes,
        reference_positive_rate=0.05,
        minimum_sample_size=5,
    )
    assert status == "critical"
    assert metrics["mean_probability_shift"] == 0.75
    assert metrics["low_confidence_rate"] == 1.0
    assert thresholds["mean_probability_shift_critical"] == 0.10


def test_rescreen_does_not_clear_a_confirmed_compliance_hold(client, auth_headers):
    source = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "phase2-hold-regression",
            "name": "Fictional Hold Regression List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/phase2-hold-list",
        },
    )
    assert source.status_code == 201, source.text

    matching_csv = (
        "source_id,name,entity_type,country,program,remarks\n"
        "HOLD-001,Fictional Confirmed Hold Exporter,entity,CN,DEMO,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    matching_version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "hold-v1", "effective_at": "2026-10-21"},
        files={"file": ("hold-v1.csv", matching_csv, "text/csv")},
    )
    assert matching_version.status_code == 201, matching_version.text
    activation = client.post(
        "/api/screening/versions/{}/activate".format(matching_version.json()["id"]),
        headers=auth_headers,
    )
    assert activation.status_code == 200, activation.text

    counterparty = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Fictional Confirmed Hold Exporter",
            "jurisdiction": "CN",
            "registration_number": "PHASE2-HOLD-001",
        },
    )
    assert counterparty.status_code == 201, counterparty.text
    counterparty_id = counterparty.json()["id"]
    first_screen = client.post(
        "/api/counterparties/{}/screen".format(counterparty_id),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert first_screen.status_code == 200, first_screen.text
    candidate = next(
        item
        for item in first_screen.json()["candidates"]
        if item["source_list_code"] == "phase2-hold-regression"
    )
    resolution = client.post(
        "/api/screening/candidates/{}/resolve".format(candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "confirmed",
            "rationale": "Confirmed fictional match for compliance-hold regression testing.",
        },
    )
    assert resolution.status_code == 200, resolution.text

    replacement_csv = (
        "source_id,name,entity_type,country,program,remarks\n"
        "HOLD-002,Fictional Replacement Entity,entity,GB,DEMO,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    replacement_version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "hold-v2", "effective_at": "2026-10-22"},
        files={"file": ("hold-v2.csv", replacement_csv, "text/csv")},
    )
    assert replacement_version.status_code == 201, replacement_version.text
    replacement_activation = client.post(
        "/api/screening/versions/{}/activate".format(replacement_version.json()["id"]),
        headers=auth_headers,
    )
    assert replacement_activation.status_code == 200, replacement_activation.text

    second_screen = client.post(
        "/api/counterparties/{}/screen".format(counterparty_id),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert second_screen.status_code == 200, second_screen.text
    refreshed = client.get(
        "/api/counterparties/{}".format(counterparty_id), headers=auth_headers
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "compliance_hold"
