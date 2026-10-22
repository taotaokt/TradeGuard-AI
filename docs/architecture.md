# Architecture notes

The initial implementation is a modular monolith. This keeps deployment and local development simple while preserving clear boundaries between authentication, counterparties, transactions, screening, rules, models, decisions, reports, and monitoring.

The API persists operational records in SQL. Long-running screening, document processing, and model workflows will move to a background worker in a later milestone. Rule, list, and model versions are retained so historical decisions can be reconstructed.

The architecture intentionally separates:

1. deterministic policy and compliance rules;
2. statistical commercial-risk predictions;
3. human review and overrides.

No model score may override a confirmed compliance hold.

Supporting files are stored outside the database. The database keeps their generated storage key,
cleaned display name, type, size, owner, and verification state. Uploads are size- and type-checked,
and normal users only soft-delete the record so historical assessment evidence remains auditable.

Screening-list sources, imported versions, normalized entries, screening runs, and review candidates
are separate records. New runs use only the active version of each source, while historical runs keep
their original version IDs. Exact and fuzzy scores create candidates; only a compliance reviewer can
classify them, and a confirmed candidate places the counterparty in a compliance-hold state.

Assessment orchestration is synchronous for the current portfolio-scale implementation. Every stage
writes an `AssessmentStep`, deterministic rules write immutable `RuleResult` records, and automatic
and reviewer decisions are kept together without losing the original recommendation. Confirmed
compliance concerns and critical deterministic rules are hard stops; lower-priority signals cannot
reduce them.

The commercial-risk component is an offline-trained, locally loaded calibrated classifier. A manifest
binds feature order, observed ranges, metrics, dependency versions, training-data hash, and artifact
hash to a named model version. Each inference creates a `Prediction` record rather than overwriting
history. Missing artifacts, schema mismatches, failed checksums, and out-of-range inputs fail safely to
human review.

FastAPI serves a no-build browser workspace and streams generated PDF assessment reports. Dashboard
and audit endpoints remain thin read models over the same transactional database. The deployment
reference runs the modular monolith and PostgreSQL as separate containers; background processing,
object storage, scheduled monitoring, and external KYB data remain explicit future boundaries.

Screening runs that produce candidate matches also create versioned monitoring alerts. Alerts retain
their source screening run, candidate references, affected transactions, reviewer ownership, and full
acknowledgement or resolution history. A reviewer can launch a new immutable assessment from an alert;
the alert stores the resulting assessment ID while audit events preserve the reason and actor. Scheduled
execution and outbound notifications remain later operational boundaries.

M9 adds a scheduler-ready portfolio rescreening entry point over the same screening service used by
interactive requests. A run snapshots active list-version IDs, skips counterparties already screened
after the latest list change, and records processed, skipped, and candidate counts. Previously confirmed
matches remain compliance holds even when a later run produces no candidates.

Transaction outcomes are stored separately from predictions so estimated risk and observed performance
cannot be confused. Adverse outcomes create risk-review alerts. Immutable drift snapshots aggregate a
bounded prediction window, compare its mean with the training reference rate, track low-confidence and
risk-band distributions, and calculate Brier score and calibration gap when outcomes are available.

M10 keeps scheduling inside the modular monolith while separating execution from the clock that triggers
it. Persistent job definitions store cadence, parameters, next-run time, and last status. A trusted worker
calls the due-job endpoint; the application advances each schedule before executing it and retains a
separate success or failure record. This prevents overlapping callers from repeatedly selecting the same
due schedule under normal operation and makes failures visible in the operations summary.

Alert creation and notification delivery use a transactional Outbox boundary. The alert and its
idempotency-keyed delivery record are committed together. External adapters claim bounded batches and
report delivery outcomes; failed attempts use exponential backoff, while stale claims can be recovered.
Provider credentials and provider-specific code remain outside the core risk application.

M11 adds a read-only portfolio projection over open transactions and their latest available predictions.
Exposure is grouped by currency, destination, and risk band; currencies are never summed without an
explicit conversion source. Stress tests persist their assumptions, exact transaction snapshot, and
currency-separated results. They calculate illustrative expected loss using exposure, adverse-outcome
probability, and loss given default, but they cannot mutate assessments or live decisions.

M12 adds a repeatable data-quality control layer over existing operational records. Each scan evaluates
versioned rules for missing evidence, stale counterparty screening, stale list versions, missing end-use
statements, and overdue outcomes. Stable issue keys make scans idempotent: recurring findings update an
existing remediation item, corrected conditions auto-resolve, and reappearing conditions reopen. Human
acknowledgement, resolution, and dismissal remain role-scoped and are written to the audit trail.

M13 replaces the previous JSON-only approval-condition output with first-class workflow records while
retaining the original JSON snapshot for historical compatibility. Each condition belongs to one
decision and assessment, has an owner role, due date, lifecycle status, and optimistic-lock version.
Fulfillment requires an active document attached to the assessed transaction; waivers and reopenings
require a rationale and create audit events. Overdue open conditions are consumed by the M12 scanner,
so operational obligations and data-quality remediation share one explainable control loop.

M14 adds entity resolution without destructive record merging. New counterparties are compared with
active records using normalized legal names and aliases. Name similarity, jurisdiction, registration
number, and website-domain agreement are persisted as review signals. A human risk reviewer classifies
each candidate; confirmed duplicates retain a canonical counterparty reference while both historical
records remain available. Pending or confirmed identity concerns route linked assessments to review and
surface in the versioned data-quality ruleset.
