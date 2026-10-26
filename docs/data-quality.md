# Data-quality controls

TradeGuard's M12 data-quality workflow turns common due-diligence gaps into tracked remediation items. It is a control layer over the existing records, not a second risk score and not an automatic trade decision.

## Workflow

1. An administrator, risk reviewer, or compliance reviewer runs `POST /api/data-quality/scans`.
2. The `dq-v6` ruleset checks active counterparties, sourced-fact verification and expiry, expired credit policies, overdue receivables, entity-resolution state, screening sources, incomplete transactions, and approval conditions.
3. Each finding is stored under a stable key composed of rule code, entity type, and entity ID.
4. Repeated findings update `last_seen_at`; they do not create duplicate issues.
5. A missing finding closes an open or acknowledged item automatically because its underlying condition has been corrected.
6. If a resolved condition appears again, the item reopens. A dismissed item remains an explicit human acceptance.
7. The responsible role can acknowledge, assign, resolve, or dismiss an item with a rationale. Administrators can manage every item.

## Rules in `dq-v6`

| Rule | Severity | Owner |
|---|---|---|
| Counterparty has no active evidence | Medium | Business user |
| Counterparty has never been screened or its screening is stale | High | Compliance reviewer |
| Counterparty has a pending or confirmed duplicate-entity concern | High | Risk reviewer |
| Counterparty fact remains unverified beyond the configured grace period | Medium | Risk reviewer |
| Verified counterparty fact is past its expiry time | High | Risk reviewer |
| Active counterparty credit policy is past its expiry time | High | Risk reviewer |
| Open or partially paid trade receivable is past due | High | Risk reviewer |
| Screening source has no active version or the active version is stale | Critical | Compliance reviewer |
| Transaction lacks an end-use statement | High | Business user |
| Transaction has no active supporting evidence | Medium | Risk reviewer |
| Transaction outcome is overdue after terms and grace period | High | Risk reviewer |
| Approval condition is past due and still open | High | Condition owner role |

The screening age, list age, outcome grace, and fact-verification grace thresholds are stored with every scan so results remain explainable. Production use should add approved evidence-expiry policies, external-source service-level agreements, escalation deadlines, and independent control validation.
