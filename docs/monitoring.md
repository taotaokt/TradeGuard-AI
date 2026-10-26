# Monitoring and outcome workflow

TradeGuard's monitoring layer is a decision-support control, not an autonomous sanctions, credit, or model-governance system. It records what was checked, what changed, and who responded.

## Portfolio rescreening

`POST /api/monitoring/runs/rescreen` screens every non-archived counterparty against all active list versions. By default, a counterparty is skipped when its latest screening run is newer than the latest active-list version. Set `force` only for an intentional full rerun.

Each run stores:

- active list-version IDs;
- eligible, processed, and skipped counterparty counts;
- candidate-match count;
- threshold, actor, start time, completion time, and status.

Candidate matches create compliance-owned alerts. A confirmed historical match remains a compliance hold until an authorized reviewer resolves the underlying candidate; a later empty screening run cannot silently clear it.

The endpoint is synchronous for the portfolio-scale demonstration. A production deployment should invoke it from a trusted scheduler, add bounded retries and locking, and emit operational alerts when a run fails or becomes stale.

## Trade outcomes

One observed outcome can be recorded for each transaction:

- `paid_on_time`;
- `delayed`;
- `dispute`;
- `material_loss`; or
- `cancelled`.

An outcome remains distinct from the earlier model prediction. Delays of 30 days or more, disputes, and material losses create risk-review alerts. A loss requires both an amount and currency. Corrections are intentionally not exposed in the current API; production use requires a controlled amendment workflow rather than overwriting history.

The receivables workflow can create the payment outcome automatically. A full settlement on or before
the due date produces `paid_on_time`; a later settlement produces `delayed` with the calculated number
of past-due days. An existing manually recorded outcome is never overwritten.

## Drift snapshots

`POST /api/monitoring/drift-snapshots` evaluates a bounded recent window for the registered champion model. It records:

- prediction count and labeled-outcome count;
- mean predicted probability and absolute shift from the training reference rate;
- low-confidence prediction rate;
- risk-band distribution;
- observed adverse-outcome rate;
- Brier score; and
- absolute calibration gap.

A snapshot is `insufficient_data` until the configured minimum prediction count is reached. The demonstration thresholds are:

| Metric | Warning | Critical |
|---|---:|---:|
| Mean probability shift | 0.05 | 0.10 |
| Low-confidence rate | 0.10 | 0.25 |
| Calibration gap | 0.10 | 0.20 |

Calibration thresholds apply only when the labeled count also reaches the minimum sample size. Warning or critical snapshots create a model-developer alert.

These simple thresholds are transparent portfolio controls, not statistically validated production limits. A real deployment needs time-aware reference distributions, PSI or divergence analysis, delayed-label handling, subgroup monitoring, independent validation, and approved escalation thresholds.

## Persistent schedules

Administrators can persist two supported job types: `portfolio_rescreen` and `model_drift`. A schedule stores its interval, validated parameters, next due time, last status, actor, and optimistic version. Calling `POST /api/monitoring/schedules/run-due` advances the next-run time before executing the selected job and records an immutable execution row with either a result reference or a bounded error message.

The application does not run an in-process clock. Deployment should use a single trusted cron, container job, or managed scheduler to call the due-job endpoint with a dedicated administrator service account. Production hardening should add database-specific row locking, worker leases, service-account scopes, and operational paging for stale running executions.

## Notification Outbox

Each screening, adverse-outcome, or model-drift alert creates one role-targeted delivery record in the same transaction. Its idempotency key prevents duplicate logical messages.

1. An approved delivery adapter calls `POST /api/notifications/claim` with a stable worker ID.
2. The adapter sends the returned payload through an approved provider.
3. It reports `delivered` or `failed` to `POST /api/notifications/{id}/result` using the same worker ID.
4. Failed work becomes claimable after bounded exponential backoff. Processing claims older than 15 minutes can be reclaimed.

The repository intentionally contains no live provider credentials or email integration. The Outbox proves the reliability boundary while keeping external delivery an explicit deployment choice.
