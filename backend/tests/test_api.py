def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "TradeGuard AI" in frontend.text
    assert "Alert center" in frontend.text

    alert_styles = client.get("/static/alerts.css")
    assert alert_styles.status_code == 200
    assert ".alert-card" in alert_styles.text


def test_authentication_required(client):
    response = client.get("/api/counterparties")
    assert response.status_code == 401


def test_login_and_current_user(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"
    assert response.json()["role"] == "admin"

    failed = client.post(
        "/api/auth/login", json={"email": "unknown@example.test", "password": "incorrect"}
    )
    assert failed.status_code == 401
    audit = client.get("/api/audit-events", headers=auth_headers)
    assert "authentication.failed" in {item["action"] for item in audit.json()}


def test_counterparty_and_transaction_workflow(client, auth_headers):
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Example Trading LLC",
            "jurisdiction": "us",
            "registration_number": "EXAMPLE-001",
            "website": "https://example.test",
            "aliases": [{"name": "Example Trading", "alias_type": "trading_name"}],
            "related_parties": [
                {"name": "Sample Owner", "relationship_type": "beneficial_owner", "country": "US"}
            ],
        },
    )
    assert counterparty_response.status_code == 201, counterparty_response.text
    counterparty = counterparty_response.json()
    assert counterparty["jurisdiction"] == "US"
    assert counterparty["version"] == 1

    transaction_response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-TEST-001",
            "product_description": "Industrial fasteners",
            "hs_code": "7318.15",
            "origin_country": "CN",
            "destination_country": "US",
            "amount": "25000.00",
            "currency": "USD",
            "payment_method": "wire_transfer",
            "payment_terms_days": 30,
            "deposit_percentage": "30.00",
            "incoterm": "FOB",
            "end_use": "Assembly of commercial warehouse shelving",
            "parties": [
                {
                    "role": "buyer",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "US",
                    "registration_number": "EXAMPLE-001",
                }
            ],
        },
    )
    assert transaction_response.status_code == 201, transaction_response.text
    transaction = transaction_response.json()

    assessment_response = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]), headers=auth_headers
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()
    assert assessment["version"] == 1
    assert assessment["status"] == "information_required"
    assert assessment["recommendation"] == "REQUEST_INFORMATION"
    assert assessment["rule_version"] == "v1"
    assert [step["name"] for step in assessment["steps"]] == [
        "validation",
        "screening",
        "rules",
        "model",
        "decision",
    ]
    assert "UNKNOWN_END_USER" in {
        result["reason_code"] for result in assessment["rule_results"]
    }


def test_assessment_rejects_missing_end_use(client, auth_headers):
    response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-TEST-MISSING-END-USE",
            "product_description": "Electronic components",
            "origin_country": "US",
            "destination_country": "SG",
            "amount": "1000.00",
            "currency": "USD",
            "payment_method": "wire_transfer",
            "parties": [{"role": "buyer", "name": "Example Buyer", "country": "SG"}],
        },
    )
    assert response.status_code == 201, response.text

    assessment = client.post(
        "/api/transactions/{}/assessments".format(response.json()["id"]), headers=auth_headers
    )
    assert assessment.status_code == 422
    assert "end_use" in assessment.json()["detail"]["fields"]


def test_counterparty_and_transaction_document_workflow(client, auth_headers):
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Evidence Test Company",
            "jurisdiction": "GB",
            "registration_number": "EVIDENCE-001",
        },
    )
    assert counterparty_response.status_code == 201, counterparty_response.text
    counterparty_id = counterparty_response.json()["id"]

    evidence_response = client.post(
        "/api/counterparties/{}/evidence".format(counterparty_id),
        headers=auth_headers,
        data={
            "document_type": "business_registration",
            "description": "Public-safe sample registration record",
        },
        files={"file": ("../registration.pdf", b"%PDF-1.4 sample", "application/pdf")},
    )
    assert evidence_response.status_code == 201, evidence_response.text
    evidence = evidence_response.json()
    assert evidence["original_filename"] == "registration.pdf"
    assert evidence["size_bytes"] == len(b"%PDF-1.4 sample")
    assert "storage_key" not in evidence

    evidence_list = client.get(
        "/api/counterparties/{}/evidence".format(counterparty_id), headers=auth_headers
    )
    assert evidence_list.status_code == 200
    assert [item["id"] for item in evidence_list.json()] == [evidence["id"]]

    download = client.get(
        "/api/documents/{}/download".format(evidence["id"]), headers=auth_headers
    )
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 sample"

    transaction_response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-EVIDENCE-001",
            "product_description": "Sample machine parts",
            "origin_country": "GB",
            "destination_country": "US",
            "amount": "5000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "end_use": "Repair of commercial equipment",
            "parties": [
                {
                    "role": "seller",
                    "name": "Evidence Test Company",
                    "counterparty_id": counterparty_id,
                    "country": "GB",
                }
            ],
        },
    )
    assert transaction_response.status_code == 201, transaction_response.text
    transaction_id = transaction_response.json()["id"]

    document_response = client.post(
        "/api/transactions/{}/documents".format(transaction_id),
        headers=auth_headers,
        data={"document_type": "purchase_order"},
        files={"file": ("purchase-order.pdf", b"%PDF-1.4 purchase order", "application/pdf")},
    )
    assert document_response.status_code == 201, document_response.text
    transaction_document = document_response.json()
    assert transaction_document["transaction_id"] == transaction_id

    remove = client.delete(
        "/api/documents/{}".format(transaction_document["id"]), headers=auth_headers
    )
    assert remove.status_code == 204

    remaining = client.get(
        "/api/transactions/{}/documents".format(transaction_id), headers=auth_headers
    )
    assert remaining.status_code == 200
    assert remaining.json() == []


def test_document_upload_rejects_unsafe_file_type(client, auth_headers):
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Unsafe Upload Test",
            "jurisdiction": "CA",
            "registration_number": "UPLOAD-REJECT-001",
        },
    )
    counterparty_id = counterparty_response.json()["id"]

    response = client.post(
        "/api/counterparties/{}/evidence".format(counterparty_id),
        headers=auth_headers,
        data={"document_type": "business_registration"},
        files={"file": ("malware.exe", b"not really an executable", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_transaction_draft_edit_and_submission_lock(client, auth_headers):
    create_response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": "PO-EDIT-001",
            "product_description": "Commercial water pumps",
            "hs_code": "8413.70",
            "quantity": "20.0000",
            "quantity_unit": "units",
            "origin_country": "cn",
            "destination_country": "us",
            "amount": "40000.00",
            "currency": "usd",
            "payment_method": "wire_transfer",
            "payment_terms_days": 15,
            "deposit_percentage": "20.00",
            "incoterm": "FOB",
            "bank_beneficiary_name": "Sample Pump Exporter",
            "bank_beneficiary_country": "cn",
            "requested_credit_exposure": "32000.00",
            "end_use": "Commercial building water circulation",
            "parties": [{"role": "seller", "name": "Sample Pump Exporter", "country": "CN"}],
        },
    )
    assert create_response.status_code == 201, create_response.text
    transaction = create_response.json()
    assert transaction["version"] == 1
    assert transaction["currency"] == "USD"
    assert transaction["bank_beneficiary_country"] == "CN"

    update_response = client.patch(
        "/api/transactions/{}".format(transaction["id"]),
        headers=auth_headers,
        json={
            "payment_terms_days": 30,
            "requested_credit_exposure": "28000.00",
            "expected_version": 1,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["version"] == 2
    assert updated["payment_terms_days"] == 30

    stale_update = client.patch(
        "/api/transactions/{}".format(transaction["id"]),
        headers=auth_headers,
        json={"payment_terms_days": 45, "expected_version": 1},
    )
    assert stale_update.status_code == 409

    assessment = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]), headers=auth_headers
    )
    assert assessment.status_code == 201, assessment.text

    locked_update = client.patch(
        "/api/transactions/{}".format(transaction["id"]),
        headers=auth_headers,
        json={"payment_terms_days": 60, "expected_version": 2},
    )
    assert locked_update.status_code == 409


def test_counterparty_archive_is_auditable_and_not_editable(client, auth_headers):
    create_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Archive Example Ltd",
            "jurisdiction": "AU",
            "registration_number": "ARCHIVE-001",
        },
    )
    assert create_response.status_code == 201, create_response.text
    counterparty = create_response.json()

    archive_response = client.post(
        "/api/counterparties/{}/archive".format(counterparty["id"]), headers=auth_headers
    )
    assert archive_response.status_code == 200, archive_response.text
    assert archive_response.json()["status"] == "archived"

    visible_response = client.get(
        "/api/counterparties/{}".format(counterparty["id"]), headers=auth_headers
    )
    assert visible_response.status_code == 200
    assert visible_response.json()["status"] == "archived"

    edit_response = client.patch(
        "/api/counterparties/{}".format(counterparty["id"]),
        headers=auth_headers,
        json={"notes": "This edit must be rejected", "expected_version": 2},
    )
    assert edit_response.status_code == 409


def _create_active_screening_list(client, auth_headers, code):
    source_response = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": code,
            "name": "Fictional Test Screening List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/screening-list",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()
    csv_content = (
        "source_id,name,entity_type,country,address,program,aliases,identifiers,remarks\n"
        "TEST-001,Example Restricted Trading Limited,entity,GB,1 Fictional Road,"
        "DEMO PROGRAM,Example Restricted Trading,,FICTIONAL TEST DATA\n"
        "TEST-002,Fictional Orion Logistics Group,entity,SG,99 Sample Road,"
        "DEMO PROGRAM,Orion Logistics Demo,,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    version_response = client.post(
        "/api/screening/lists/{}/versions/import".format(source["id"]),
        headers=auth_headers,
        data={"version": "test-v1", "effective_at": "2026-10-20T00:00:00Z"},
        files={"file": ("fictional-list.csv", csv_content, "text/csv")},
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    assert version["entry_count"] == 2
    assert len(version["checksum_sha256"]) == 64

    activate_response = client.post(
        "/api/screening/versions/{}/activate".format(version["id"]), headers=auth_headers
    )
    assert activate_response.status_code == 200, activate_response.text
    assert activate_response.json()["status"] == "active"
    return source, version


def test_versioned_screening_exact_fuzzy_and_false_positive_resolution(client, auth_headers):
    source, version = _create_active_screening_list(client, auth_headers, "test-screening-main")
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Example Restricted Trading LLC",
            "jurisdiction": "GB",
            "registration_number": "SCREEN-001",
            "related_parties": [
                {
                    "name": "Fictional Orian Logistics",
                    "relationship_type": "consignee",
                    "country": "SG",
                }
            ],
        },
    )
    assert counterparty_response.status_code == 201, counterparty_response.text
    counterparty = counterparty_response.json()

    screening_response = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 85},
    )
    assert screening_response.status_code == 200, screening_response.text
    screening_run = screening_response.json()
    assert screening_run["status"] == "completed"
    candidates = screening_run["candidates"]
    assert {candidate["match_type"] for candidate in candidates} == {"exact", "fuzzy"}
    assert {candidate["list_version_id"] for candidate in candidates} == {version["id"]}
    assert all(candidate["status"] == "pending" for candidate in candidates)
    exact_candidate = next(item for item in candidates if item["match_type"] == "exact")
    assert exact_candidate["screened_country"] == "GB"
    assert exact_candidate["screened_identifier"] == "SCREEN-001"

    no_rationale = client.post(
        "/api/screening/candidates/{}/resolve".format(candidates[0]["id"]),
        headers=auth_headers,
        json={"classification": "cleared", "rationale": "no"},
    )
    assert no_rationale.status_code == 422

    for candidate in candidates:
        resolution = client.post(
            "/api/screening/candidates/{}/resolve".format(candidate["id"]),
            headers=auth_headers,
            json={
                "classification": "cleared",
                "rationale": "Fictional test name; registration and address do not match.",
            },
        )
        assert resolution.status_code == 200, resolution.text
        assert resolution.json()["status"] == "cleared"

    counterparty_after_review = client.get(
        "/api/counterparties/{}".format(counterparty["id"]), headers=auth_headers
    )
    assert counterparty_after_review.status_code == 200
    assert counterparty_after_review.json()["status"] == "active"

    invalid_update = (
        "source_id,name\nDUPLICATE,First Name\nDUPLICATE,Second Name\n"
    ).encode("utf-8")
    failed_import = client.post(
        "/api/screening/lists/{}/versions/import".format(source["id"]),
        headers=auth_headers,
        data={"version": "broken-v2", "effective_at": "2026-10-21"},
        files={"file": ("broken.csv", invalid_update, "text/csv")},
    )
    assert failed_import.status_code == 422

    listed_sources = client.get("/api/screening/lists", headers=auth_headers)
    selected_source = next(item for item in listed_sources.json() if item["id"] == source["id"])
    assert selected_source["active_version_id"] == version["id"]

    replacement_csv = (
        "source_id,name,entity_type,country,remarks\n"
        "TEST-V2-001,Version Two Fictional Entity,entity,US,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    replacement_import = client.post(
        "/api/screening/lists/{}/versions/import".format(source["id"]),
        headers=auth_headers,
        data={"version": "test-v2", "effective_at": "2026-10-21"},
        files={"file": ("fictional-list-v2.csv", replacement_csv, "text/csv")},
    )
    assert replacement_import.status_code == 201, replacement_import.text
    replacement = replacement_import.json()
    replacement_activation = client.post(
        "/api/screening/versions/{}/activate".format(replacement["id"]), headers=auth_headers
    )
    assert replacement_activation.status_code == 200

    versions_response = client.get(
        "/api/screening/lists/{}/versions".format(source["id"]), headers=auth_headers
    )
    versions_by_id = {item["id"]: item for item in versions_response.json()}
    assert versions_by_id[version["id"]]["status"] == "retired"
    assert versions_by_id[replacement["id"]]["status"] == "active"


def test_confirmed_screening_candidate_creates_compliance_hold(client, auth_headers):
    _create_active_screening_list(client, auth_headers, "test-screening-confirmed")
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Example Restricted Trading",
            "jurisdiction": "GB",
            "registration_number": "SCREEN-CONFIRMED-001",
            "related_parties": [
                {
                    "name": "Fictional Orian Logistics",
                    "relationship_type": "consignee",
                    "country": "SG",
                }
            ],
        },
    )
    counterparty = counterparty_response.json()
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 85},
    )
    assert screening.status_code == 200, screening.text
    exact_candidate = next(
        item for item in screening.json()["candidates"] if item["match_type"] == "exact"
    )

    resolution = client.post(
        "/api/screening/candidates/{}/resolve".format(exact_candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "confirmed",
            "rationale": "Test reviewer confirmed matching identifiers and address.",
        },
    )
    assert resolution.status_code == 200, resolution.text

    another_candidate = next(
        item for item in screening.json()["candidates"] if item["id"] != exact_candidate["id"]
    )
    cleared_other_candidate = client.post(
        "/api/screening/candidates/{}/resolve".format(another_candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "cleared",
            "rationale": "The second fictional candidate has different identifiers.",
        },
    )
    assert cleared_other_candidate.status_code == 200

    counterparty_after_review = client.get(
        "/api/counterparties/{}".format(counterparty["id"]), headers=auth_headers
    )
    assert counterparty_after_review.json()["status"] == "compliance_hold"


def _create_clean_screened_counterparty(client, auth_headers, suffix):
    _create_active_screening_list(client, auth_headers, "decision-list-{}".format(suffix))
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Clear Alpine Components {}".format(suffix),
            "jurisdiction": "CH",
            "registration_number": "CLEAR-{}".format(suffix),
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
    return counterparty


def _create_decision_transaction(
    client,
    auth_headers,
    *,
    reference,
    counterparty,
    payment_terms_days=15,
    bank_beneficiary_name=None,
):
    response = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": reference,
            "product_description": "Commercial refrigeration components",
            "hs_code": "8418.99",
            "quantity": "100.0000",
            "quantity_unit": "units",
            "origin_country": "CH",
            "destination_country": "US",
            "amount": "60000.00",
            "currency": "USD",
            "payment_method": "letter_of_credit",
            "payment_terms_days": payment_terms_days,
            "deposit_percentage": "30.00",
            "bank_beneficiary_name": bank_beneficiary_name or counterparty["legal_name"],
            "bank_beneficiary_country": "CH",
            "requested_credit_exposure": "42000.00",
            "end_use": "Installation in commercial food-storage facilities",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": "CH",
                    "registration_number": counterparty["registration_number"],
                },
                {
                    "role": "end_user",
                    "name": "Public Safe Demonstration Customer",
                    "country": "US",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_clean_assessment_is_approved_with_reproducible_steps(client, auth_headers):
    counterparty = _create_clean_screened_counterparty(client, auth_headers, "approve")
    transaction = _create_decision_transaction(
        client,
        auth_headers,
        reference="PO-DECISION-APPROVE",
        counterparty=counterparty,
    )

    response = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]), headers=auth_headers
    )
    assert response.status_code == 201, response.text
    assessment = response.json()
    assert assessment["status"] == "completed"
    assert assessment["recommendation"] == "APPROVE"
    assert assessment["decision"]["hard_stop"] is False
    assert assessment["decision"]["final_recommendation"] == "APPROVE"
    assert assessment["review_case"] is None
    assert len(assessment["rule_checksum_sha256"]) == 64
    assert assessment["steps"][3]["status"] == "completed"
    assert assessment["model_version"] == "synthetic-2026-10-21-v1"
    assert 0 <= float(assessment["prediction"]["probability"]) <= 1
    assert assessment["prediction"]["calibrated"] is True
    assert assessment["prediction"]["risk_band"] == "low"

    report = client.get(
        "/api/assessments/{}/report".format(assessment["id"]), headers=auth_headers
    )
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")
    from io import BytesIO
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(report.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) >= 2
    assert "Assessment Report" in text
    assert "synthetic" in text.lower()

    saved = client.get("/api/assessments/{}".format(assessment["id"]), headers=auth_headers)
    assert saved.status_code == 200
    assert saved.json()["input_snapshot_json"] == assessment["input_snapshot_json"]

    summary = client.get("/api/dashboard/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert summary.json()["transactions"] >= 1

    audit = client.get("/api/audit-events", headers=auth_headers)
    assert audit.status_code == 200
    assert "assessment.report_downloaded" in {item["action"] for item in audit.json()}


def test_long_terms_route_to_review_and_reviewer_adds_conditions(client, auth_headers):
    counterparty = _create_clean_screened_counterparty(client, auth_headers, "review")
    transaction = _create_decision_transaction(
        client,
        auth_headers,
        reference="PO-DECISION-REVIEW",
        counterparty=counterparty,
        payment_terms_days=60,
    )
    assessment_response = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]), headers=auth_headers
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()
    assert assessment["recommendation"] == "REFER"
    assert assessment["status"] == "pending_review"
    assert assessment["review_case"]["required_role"] == "risk_reviewer"
    assert "NEW_COUNTERPARTY_LONG_TERMS" in {
        result["reason_code"] for result in assessment["rule_results"]
    }

    no_conditions = client.post(
        "/api/assessments/{}/reviews".format(assessment["id"]),
        headers=auth_headers,
        json={
            "decision": "APPROVE_WITH_CONDITIONS",
            "rationale": "Risk can be controlled with a payment instrument.",
            "conditions": [],
        },
    )
    assert no_conditions.status_code == 422

    reviewed = client.post(
        "/api/assessments/{}/reviews".format(assessment["id"]),
        headers=auth_headers,
        json={
            "decision": "APPROVE_WITH_CONDITIONS",
            "rationale": "Risk can be controlled with an irrevocable letter of credit.",
            "conditions": ["Obtain an irrevocable letter of credit before shipment"],
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    result = reviewed.json()
    assert result["status"] == "completed"
    assert result["decision"]["final_recommendation"] == "APPROVE_WITH_CONDITIONS"
    assert result["decision"]["is_override"] is True
    assert result["review_case"]["status"] == "approved_with_conditions"


def test_confirmed_compliance_hold_has_highest_precedence(client, auth_headers):
    _create_active_screening_list(client, auth_headers, "decision-list-hard-stop")
    counterparty_response = client.post(
        "/api/counterparties",
        headers=auth_headers,
        json={
            "legal_name": "Example Restricted Trading",
            "jurisdiction": "GB",
            "registration_number": "HARD-STOP-001",
        },
    )
    counterparty = counterparty_response.json()
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    candidate = next(
        item for item in screening.json()["candidates"] if item["match_type"] == "exact"
    )
    confirmation = client.post(
        "/api/screening/candidates/{}/resolve".format(candidate["id"]),
        headers=auth_headers,
        json={
            "classification": "confirmed",
            "rationale": "Test identifiers and address were confirmed as matching.",
        },
    )
    assert confirmation.status_code == 200

    transaction = _create_decision_transaction(
        client,
        auth_headers,
        reference="PO-DECISION-HARD-STOP",
        counterparty=counterparty,
        payment_terms_days=0,
    )
    assessment_response = client.post(
        "/api/transactions/{}/assessments".format(transaction["id"]), headers=auth_headers
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()
    assert assessment["recommendation"] == "COMPLIANCE_HOLD"
    assert assessment["decision"]["hard_stop"] is True
    assert assessment["review_case"]["required_role"] == "compliance_reviewer"

    forbidden_override = client.post(
        "/api/assessments/{}/reviews".format(assessment["id"]),
        headers=auth_headers,
        json={
            "decision": "APPROVE",
            "rationale": "This attempt must not override a confirmed compliance hold.",
        },
    )
    assert forbidden_override.status_code == 409
