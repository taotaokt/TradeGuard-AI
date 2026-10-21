from datetime import datetime, timedelta

from backend.app.db import SessionLocal
from backend.app.models import NotificationDelivery, ScheduledJob


def _create_alert_with_notification(client, auth_headers):
    source = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "phase3-outbox-list",
            "name": "Fictional Phase 3 Outbox List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/phase3-outbox-list",
        },
    )
    assert source.status_code == 201, source.text
    csv_content = (
        "source_id,name,entity_type,country,program,remarks\n"
        "PHASE3-001,Fictional Outbox Exporter,entity,US,DEMO,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "phase3-v1", "effective_at": "2026-10-21"},
        files={"file": ("phase3-list.csv", csv_content, "text/csv")},
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
            "legal_name": "Fictional Outbox Exporter",
            "jurisdiction": "US",
            "registration_number": "PHASE3-OUTBOX-001",
        },
    )
    assert counterparty.status_code == 201, counterparty.text
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty.json()["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    assert screening.json()["candidates"]


def test_schedules_notification_outbox_and_operations_summary(client, auth_headers):
    _create_alert_with_notification(client, auth_headers)

    pending = client.get("/api/notifications?status=pending", headers=auth_headers)
    assert pending.status_code == 200, pending.text
    delivery = pending.json()[0]
    assert "New screening candidates" in delivery["payload_json"]
    assert delivery["recipient_role"] == "compliance_reviewer"
    assert delivery["attempt_count"] == 0

    claimed = client.post(
        "/api/notifications/claim",
        headers=auth_headers,
        json={"worker_id": "test-delivery-worker", "limit": 100},
    )
    assert claimed.status_code == 200, claimed.text
    claimed_delivery = next(item for item in claimed.json() if item["id"] == delivery["id"])
    assert claimed_delivery["status"] == "processing"
    assert claimed_delivery["attempt_count"] == 1

    wrong_worker = client.post(
        "/api/notifications/{}/result".format(delivery["id"]),
        headers=auth_headers,
        json={"worker_id": "different-worker", "status": "delivered"},
    )
    assert wrong_worker.status_code == 409
    missing_error = client.post(
        "/api/notifications/{}/result".format(delivery["id"]),
        headers=auth_headers,
        json={"worker_id": "test-delivery-worker", "status": "failed"},
    )
    assert missing_error.status_code == 422
    failed = client.post(
        "/api/notifications/{}/result".format(delivery["id"]),
        headers=auth_headers,
        json={
            "worker_id": "test-delivery-worker",
            "status": "failed",
            "error": "Fictional provider timeout",
        },
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "failed"
    assert failed.json()["last_error"] == "Fictional provider timeout"

    with SessionLocal() as db:
        stored = db.get(NotificationDelivery, delivery["id"])
        stored.available_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    retry_claim = client.post(
        "/api/notifications/claim",
        headers=auth_headers,
        json={"worker_id": "retry-worker", "limit": 100},
    )
    assert retry_claim.status_code == 200, retry_claim.text
    retried = next(item for item in retry_claim.json() if item["id"] == delivery["id"])
    assert retried["attempt_count"] == 2
    delivered = client.post(
        "/api/notifications/{}/result".format(delivery["id"]),
        headers=auth_headers,
        json={"worker_id": "retry-worker", "status": "delivered"},
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivered_at"] is not None

    due_at = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    schedule = client.put(
        "/api/monitoring/schedules/portfolio_rescreen",
        headers=auth_headers,
        json={
            "enabled": True,
            "interval_minutes": 1440,
            "next_run_at": due_at,
            "force": False,
            "fuzzy_threshold": 90,
        },
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["job_key"] == "portfolio_rescreen"
    assert schedule.json()["version"] == 1

    executions = client.post(
        "/api/monitoring/schedules/run-due",
        headers=auth_headers,
        json={"limit": 10},
    )
    assert executions.status_code == 200, executions.text
    execution = next(
        item
        for item in executions.json()
        if item["scheduled_job_id"] == schedule.json()["id"]
    )
    assert execution["status"] == "completed"
    assert "monitoring_run_id" in execution["result_reference_json"]

    no_longer_due = client.post(
        "/api/monitoring/schedules/run-due",
        headers=auth_headers,
        json={"limit": 10},
    )
    assert no_longer_due.status_code == 200
    assert no_longer_due.json() == []

    history = client.get("/api/monitoring/schedule-executions", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()[0]["id"] == execution["id"]
    summary = client.get("/api/monitoring/operations-summary", headers=auth_headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["enabled_schedules"] >= 1
    assert summary.json()["overdue_schedules"] == 0
    assert summary.json()["latest_rescreen_status"] == "completed"

    failing_schedule = client.put(
        "/api/monitoring/schedules/model_drift",
        headers=auth_headers,
        json={
            "enabled": True,
            "interval_minutes": 10080,
            "next_run_at": due_at,
            "window_days": 90,
            "minimum_sample_size": 20,
        },
    )
    assert failing_schedule.status_code == 200, failing_schedule.text
    with SessionLocal() as db:
        stored_schedule = db.get(ScheduledJob, failing_schedule.json()["id"])
        stored_schedule.parameters_json = "not-json"
        db.commit()
    failed_execution = client.post(
        "/api/monitoring/schedules/run-due",
        headers=auth_headers,
        json={"limit": 10},
    )
    assert failed_execution.status_code == 200, failed_execution.text
    assert failed_execution.json()[0]["status"] == "failed"
    assert failed_execution.json()[0]["error_message"]
    attention = client.get("/api/monitoring/operations-summary", headers=auth_headers)
    assert attention.status_code == 200
    assert attention.json()["health"] == "attention"
    assert attention.json()["failed_executions_24h"] >= 1


def test_schedule_validation(client, auth_headers):
    unsupported = client.put(
        "/api/monitoring/schedules/unknown-job",
        headers=auth_headers,
        json={"interval_minutes": 60},
    )
    assert unsupported.status_code == 422

    invalid_interval = client.put(
        "/api/monitoring/schedules/model_drift",
        headers=auth_headers,
        json={"interval_minutes": 5},
    )
    assert invalid_interval.status_code == 422
