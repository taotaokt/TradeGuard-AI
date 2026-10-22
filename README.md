# TradeGuard AI

TradeGuard AI is a counterparty and transaction risk-assessment tool for small import and export businesses.

It is not an automatic trade-approval system. It brings company records, transaction details, supporting documents, screening results, and risk rules into one reviewable workflow. Important compliance decisions always remain visible to a human reviewer.

> This is a portfolio and research project for fintech, risk, and applied machine-learning roles. It is designed to grow from a public demonstration into a practical internal tool.

## What it can do

The current version can:

- authenticate users and enforce role-based permissions;
- create customer, supplier, and other counterparty profiles;
- record company aliases, registration details, and related parties;
- create import and export transactions;
- record routes, values, payment terms, beneficiaries, and end use;
- upload registration evidence, contracts, invoices, and other documents;
- import versioned screening lists with checksums;
- run exact and fuzzy screening against companies, aliases, and related parties;
- let reviewers clear false positives or confirm a compliance hold;
- run validation, screening, rules, and decision steps in a fixed order;
- calculate a calibrated synthetic commercial-risk probability with uncertainty checks;
- verify the model artifact checksum and store the model/data/runtime versions used;
- return reason codes, risk dimensions, recommendations, and review tasks;
- let reviewers approve, approve with conditions, request information, reject, or maintain a compliance hold;
- provide a responsive browser workspace, dashboard, review queue, and audit trail;
- export a two-page PDF assessment report with evidence and limitations;
- create monitoring alerts when a new screening run finds candidate matches;
- assign, acknowledge, resolve, dismiss, or launch a versioned reassessment from an alert;
- run a scheduler-ready portfolio rescreen that skips counterparties already checked against current lists;
- record payment delays, disputes, losses, cancellations, and on-time outcomes;
- create model-monitoring snapshots for prediction shift, low-confidence rate, Brier score, and calibration gap;
- configure persistent portfolio and model-monitoring schedules with execution history;
- queue alert notifications in an idempotent, retryable Outbox for an external delivery worker;
- aggregate open exposure without mixing currencies;
- run reproducible downside scenarios without changing live decisions.

The included model is deliberately trained on generated data. It demonstrates a governed ML workflow, not real creditworthiness or production readiness.

See [REQUIREMENTS.md](./REQUIREMENTS.md) for the full product requirements and workflows, or [docs/architecture.md](./docs/architecture.md) for a shorter architecture overview.

## Project status

- [x] M1: foundation, authentication, permissions, database, and migrations
- [x] M2: counterparty, transaction, and supporting-document workflows
- [x] M3: counterparty and related-party screening
- [x] M4: rules engine, assessment orchestration, and review decisions
- [x] M5: credit-risk models, calibration, inference safeguards, and model documentation
- [x] M6: frontend, PDF reports, dashboard, and complete audit interface
- [x] M7: deployment reference, CI, public demo data, and application materials
- [x] M8: monitoring alerts, reviewer ownership, and alert-driven reassessment
- [x] M9: portfolio rescreening, trade outcomes, and model-drift snapshots
- [x] M10: persistent schedules, execution history, notification Outbox, and operations dashboard
- [x] M11: portfolio exposure analytics and reproducible stress testing

## Run it for the first time

These steps work on macOS or Linux with Python 3.9 or newer.

### Step 1: open the project directory

```bash
cd CreditEva
```

### Step 2: create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation, your terminal prompt will usually begin with `(.venv)`.

### Step 3: install the project

```bash
python3 -m pip install -e '.[dev]'
```

### Step 4: prepare the configuration and database

```bash
cp .env.example .env
make migrate
```

The default setup uses a local SQLite database, so no separate database server is required.

### Step 5: optionally add the public demo

```bash
python3 scripts/seed_demo.py
```

The command is idempotent: running it again returns the same demonstration records rather than creating duplicates. Every name, identifier, list entry, and transaction in the demo is fictional.

### Step 6: start the application

```bash
make run
```

Then open:

- browser workspace: <http://localhost:8000>
- interactive API documentation: <http://localhost:8000/docs>
- health check: <http://localhost:8000/api/health>

The default development account is:

```text
Email: admin@tradeguard.local
Password: change-me-now
```

This account is only for local development. Change both the password and `SECRET_KEY` in `.env` before using any real or sensitive data.

## Try the first workflow

Open `/docs`, then follow these steps:

1. Call `POST /api/auth/login` and copy the returned `access_token`.
2. Select **Authorize** and paste only the token. Swagger will add `Bearer` automatically.
3. Call `POST /api/counterparties` to create a company.
4. Call `POST /api/counterparties/{id}/evidence` to upload registration evidence.
5. Call `POST /api/transactions` to create a transaction.
6. Call `POST /api/transactions/{id}/documents` to upload a contract or invoice.
7. Call `POST /api/transactions/{id}/assessments` to run the assessment workflow.

If the transaction is missing an end use or a main transaction party, the API returns the fields that need attention instead of producing a misleading result.

## Try screening

The repository includes a completely fictional list for testing:

```text
sample-data/screening/demo_restricted_parties.csv
```

In `/docs`:

1. Call `POST /api/screening/lists` to create a list source.
2. Call `POST /api/screening/lists/{id}/versions/import` to upload the sample CSV.
3. Call `POST /api/screening/versions/{id}/activate` to activate that version.
4. Create a test counterparty with an identical or similar name.
5. Call `POST /api/counterparties/{id}/screen`.
6. Call `POST /api/screening/candidates/{id}/resolve` to record a human conclusion and rationale.

A fuzzy name score only creates a candidate for review. It never confirms a sanctions or restricted-party match automatically. See [docs/screening-sources.md](./docs/screening-sources.md) for the source policy and CSV format.

## Read an assessment result

The response from `POST /api/transactions/{id}/assessments` contains:

- `steps`: validation, screening, rules, model, and decision stages;
- `rule_results`: triggered reason codes, severity, inputs, and explanations;
- `decision`: the automatic recommendation, risk dimensions, and hard-stop status; and
- `review_case`: the required reviewer role and current review status.

The `prediction` record adds the calibrated probability, risk band, confidence, uncertainty reason, feature snapshot, and policy-oriented reason codes. The model stage becomes `incomplete` and routes to review if a verified artifact cannot be loaded. A confirmed compliance concern remains a hard stop regardless of the probability.

Download the matching PDF from `GET /api/assessments/{id}/report`. A visually verified fictional example is available at [output/pdf/demo-assessment-report.pdf](./output/pdf/demo-assessment-report.pdf).

See [docs/decisioning.md](./docs/decisioning.md) for precedence and [ml/model_cards/synthetic-2026-10-21-v1.md](./ml/model_cards/synthetic-2026-10-21-v1.md) for intended use and limitations.

## Reproduce the model experiment

```bash
python3 -m ml.scripts.generate_synthetic_data
python3 -m ml.scripts.train_models
python3 -m pytest backend/tests/test_ml.py
```

The pipeline uses a fixed seed, a stratified train/test split, sigmoid calibration, and held-out metrics. It compares logistic regression with a random forest, records dependency and data checksums, and chooses the lowest Brier score with ROC AUC as a tie-breaker. The current synthetic result is documented in [docs/research-report.md](./docs/research-report.md).

## Work with monitoring alerts

Each screening run that produces one or more candidate matches now creates a monitoring alert. Open **Alert center** in the browser workspace, or use the API:

1. Call `GET /api/alerts` to view alerts and their linked counterparty, screening run, and affected transactions.
2. Call `POST /api/alerts/{id}/actions` to assign, acknowledge, resolve, or dismiss an alert with a rationale.
3. Call `POST /api/alerts/{id}/reassess` with a linked transaction ID to create a new immutable assessment version.

The alert closes only after a reviewer records a terminal action or launches the reassessment. Both the alert action and the new assessment are retained in the audit trail.

## Run portfolio and model monitoring

The **Alert center** now includes controls for portfolio rescreening and model-drift checks. The matching API workflow is:

1. Call `POST /api/monitoring/runs/rescreen` after activating a new list version. Counterparties already screened after the latest active-list change are skipped unless `force` is true.
2. Call `POST /api/transactions/{id}/outcome` when an invoice is paid, delayed, disputed, cancelled, or produces a material loss. Adverse outcomes create a risk-review alert.
3. Call `POST /api/monitoring/drift-snapshots` to compare the recent prediction window with the model's documented reference rate and any available outcomes.

The synchronous rescreen endpoint is intentionally scheduler-ready: a trusted cron service or managed job runner can invoke it later without moving decision logic out of the application. See [docs/monitoring.md](./docs/monitoring.md) for metrics, thresholds, limitations, and operational guidance.

## Configure operational automation

Administrators can use the **Operations** workspace or the API to configure daily portfolio rescreening and weekly model-drift checks. `POST /api/monitoring/schedules/run-due` atomically advances each due schedule before executing it and records a completed or failed execution. A production scheduler can call this endpoint with a dedicated service account.

Every newly created alert also writes an idempotent notification record in the same database transaction. A delivery adapter claims work from `POST /api/notifications/claim`, sends it through an approved email or messaging provider, and reports success or failure to `POST /api/notifications/{id}/result`. Failed deliveries use bounded exponential backoff, and abandoned claims become eligible again after 15 minutes. No real external message is sent by this repository.

## Analyze portfolio exposure

The **Portfolio** workspace groups open exposure by currency, destination, and latest risk band. Currencies remain separate throughout the API and interface; the application does not produce a misleading cross-currency total without exchange-rate data.

Risk reviewers can save downside scenarios with exposure growth, probability multipliers, loss-given-default assumptions, unscored-transaction assumptions, and optional country-specific probability add-ons. Each result stores the parameters and exact transaction snapshot used. Stress tests are analytical only: they never modify transactions, assessments, recommendations, or review decisions. See [docs/portfolio-analytics.md](./docs/portfolio-analytics.md).

## Run the tests

```bash
make test
```

To include coverage:

```bash
python3 -m pytest --cov=backend.app --cov-report=term-missing
```

The test suite covers critical API workflows, hard-stop precedence, monitoring-alert lifecycle, alert-driven reassessment, scheduled execution, notification retry behavior, portfolio aggregation, stress-test immutability, model reproducibility, artifact verification, PDF generation, audit access, and migrations.

## PostgreSQL and Docker

Docker is optional. After installing Docker Desktop, run:

```bash
docker compose up --build
```

The API container applies database migrations before starting. SQLite is simpler for a first local run; the Compose setup uses PostgreSQL.

For a stricter deployment reference with required secrets, an unprivileged application user, persistent uploads, service health checks, and backup guidance, see [docs/deployment.md](./docs/deployment.md).

## Project structure

```text
backend/app/          API routes, models, permissions, and business logic
backend/tests/        automated tests
config/rules/         versioned risk-rule configuration
config/lists/         official screening-source references
migrations/           database schema history
ml/                   data generation, training, artifacts, and model cards
docs/                 architecture, research, deployment, and portfolio notes
frontend/             responsive HTML, CSS, and JavaScript workspace
sample-data/          public-safe demonstration data
scripts/              demo seeding and report generation
output/pdf/            visually verified fictional report example
REQUIREMENTS.md       full product requirements and workflows
```

## Portfolio and application material

- [English project summary](./docs/portfolio-summary-en.md)
- [中文项目简介](./docs/portfolio-summary-zh.md)
- [Research report](./docs/research-report.md)
- [Resume and master's application bullets](./docs/resume-bullets.md)

## Important limitations

TradeGuard AI is a decision-support project, not legal advice. It does not determine export-license requirements, and a fuzzy name match must never be treated as a confirmed sanctions match. Compliance concerns require supporting evidence and human review.

The statistical model uses synthetic data and is unsuitable for real lending, credit denial, trade-limit setting, or family-business decisions. Real use requires lawful outcome data, independent validation, privacy and retention controls, security review, operational monitoring, and explicit governance. Do not upload confidential records to a public demo.
