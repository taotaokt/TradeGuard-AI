import json
from decimal import Decimal


def _prepare_portfolio_counterparty(client, auth_headers):
    source = client.post(
        "/api/screening/lists",
        headers=auth_headers,
        json={
            "code": "portfolio-analysis-list",
            "name": "Fictional Portfolio Analysis List",
            "authority": "TradeGuard Test Suite",
            "source_url": "https://example.test/portfolio-analysis-list",
        },
    )
    assert source.status_code == 201, source.text
    csv_content = (
        "source_id,name,entity_type,country,program,remarks\n"
        "PORT-001,Fictional Unrelated Portfolio Entity,entity,GB,DEMO,FICTIONAL TEST DATA\n"
    ).encode("utf-8")
    version = client.post(
        "/api/screening/lists/{}/versions/import".format(source.json()["id"]),
        headers=auth_headers,
        data={"version": "portfolio-v1", "effective_at": "2026-10-21"},
        files={"file": ("portfolio-list.csv", csv_content, "text/csv")},
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
            "legal_name": "Fictional Portfolio Components Ltd",
            "jurisdiction": "SG",
            "registration_number": "PORTFOLIO-CP-001",
        },
    )
    assert counterparty.status_code == 201, counterparty.text
    screening = client.post(
        "/api/counterparties/{}/screen".format(counterparty.json()["id"]),
        headers=auth_headers,
        json={"fuzzy_threshold": 90},
    )
    assert screening.status_code == 200, screening.text
    return counterparty.json()


def _create_assessed_transaction(
    client,
    auth_headers,
    *,
    counterparty,
    reference,
    destination,
    currency,
    amount,
    exposure,
):
    transaction = client.post(
        "/api/transactions",
        headers=auth_headers,
        json={
            "reference": reference,
            "product_description": "Fictional industrial control components",
            "origin_country": "SG",
            "destination_country": destination,
            "amount": amount,
            "currency": currency,
            "payment_method": "letter_of_credit",
            "payment_terms_days": 30,
            "deposit_percentage": "30.00",
            "requested_credit_exposure": exposure,
            "end_use": "Installation in fictional commercial equipment",
            "parties": [
                {
                    "role": "seller",
                    "name": counterparty["legal_name"],
                    "counterparty_id": counterparty["id"],
                    "country": counterparty["jurisdiction"],
                    "registration_number": counterparty["registration_number"],
                },
                {"role": "end_user", "name": "Fictional End User", "country": destination},
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    assessment = client.post(
        "/api/transactions/{}/assessments".format(transaction.json()["id"]),
        headers=auth_headers,
    )
    assert assessment.status_code == 201, assessment.text
    assert assessment.json()["prediction"] is not None
    return transaction.json()["id"]


def test_portfolio_summary_and_reproducible_stress_test(client, auth_headers):
    counterparty = _prepare_portfolio_counterparty(client, auth_headers)
    usd_transaction_id = _create_assessed_transaction(
        client,
        auth_headers,
        counterparty=counterparty,
        reference="PO-PORTFOLIO-USD-001",
        destination="US",
        currency="USD",
        amount="80000.00",
        exposure="50000.00",
    )
    _create_assessed_transaction(
        client,
        auth_headers,
        counterparty=counterparty,
        reference="PO-PORTFOLIO-CNY-001",
        destination="CN",
        currency="CNY",
        amount="600000.00",
        exposure="400000.00",
    )

    summary = client.get("/api/portfolio/summary", headers=auth_headers)
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["open_transaction_count"] >= 2
    assert data["assessed_transaction_count"] >= 2
    assert data["open_transaction_count"] == (
        data["assessed_transaction_count"] + data["unscored_transaction_count"]
    )
    currency_buckets = {
        (item["key"], item["currency"]): Decimal(item["exposure"])
        for item in data["exposure_by_currency"]
    }
    assert currency_buckets[("USD", "USD")] >= Decimal("50000.00")
    assert currency_buckets[("CNY", "CNY")] >= Decimal("400000.00")

    before = client.get(
        "/api/transactions/{}".format(usd_transaction_id), headers=auth_headers
    ).json()
    stress = client.post(
        "/api/portfolio/stress-tests",
        headers=auth_headers,
        json={
            "name": "China demand and exposure shock",
            "rationale": "Assess a fictional downside scenario without changing live decisions.",
            "probability_multiplier": "1.75",
            "exposure_growth_percentage": "10.00",
            "loss_given_default": "0.60",
            "unscored_probability": "0.15",
            "selected_countries": ["cn"],
            "country_probability_addon": "0.10",
        },
    )
    assert stress.status_code == 201, stress.text
    stress_data = stress.json()
    assert stress_data["status"] == "completed"
    parameters = json.loads(stress_data["parameters_json"])
    snapshot = json.loads(stress_data["portfolio_snapshot_json"])
    result = json.loads(stress_data["result_json"])
    assert parameters["selected_countries"] == ["CN"]
    assert len(snapshot["transactions"]) >= 2
    assert result["affected_transactions"] >= 2
    assert result["selected_country_transaction_count"] >= 1
    assert result["decision_effect"] == "none"
    for currency_result in result["by_currency"]:
        assert Decimal(currency_result["stressed_exposure"]) > Decimal(
            currency_result["baseline_exposure"]
        )
        assert Decimal(currency_result["stressed_expected_loss"]) >= Decimal(
            currency_result["baseline_expected_loss"]
        )

    after = client.get(
        "/api/transactions/{}".format(usd_transaction_id), headers=auth_headers
    ).json()
    assert after["status"] == before["status"]
    assert after["version"] == before["version"]

    history = client.get("/api/portfolio/stress-tests", headers=auth_headers)
    detail = client.get(
        "/api/portfolio/stress-tests/{}".format(stress_data["id"]),
        headers=auth_headers,
    )
    assert history.status_code == 200
    assert history.json()[0]["id"] == stress_data["id"]
    assert detail.status_code == 200
    assert detail.json()["result_json"] == stress_data["result_json"]


def test_portfolio_stress_validation_and_missing_result(client, auth_headers):
    invalid = client.post(
        "/api/portfolio/stress-tests",
        headers=auth_headers,
        json={
            "name": "Invalid country scenario",
            "rationale": "This scenario deliberately omits selected country codes.",
            "country_probability_addon": "0.10",
        },
    )
    assert invalid.status_code == 422
    missing = client.get(
        "/api/portfolio/stress-tests/not-a-real-id", headers=auth_headers
    )
    assert missing.status_code == 404
