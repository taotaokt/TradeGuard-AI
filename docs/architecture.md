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
