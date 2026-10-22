# KYB fact provenance

M15 turns key company information into structured, source-backed records. A fact can represent a tax identifier, registered address, director, owner, beneficial owner, industry code, bank account, or another relevant company attribute.

## Workflow

1. Attach an evidence document to the counterparty or identify an approved HTTP(S) source.
2. Create the fact with `POST /api/counterparties/{id}/facts`.
3. The API stores the original value and a normalized comparison value, then derives a stable key from the counterparty, type, value, and source. Repeating the same combination returns a conflict.
4. An administrator, risk reviewer, or compliance reviewer verifies or rejects the fact with a rationale and expected version.
5. A fact that is no longer applicable is retired instead of deleted. Its source and review history remain available for audit.
6. New assessments snapshot every active fact and its source, verification status, validity dates, and version.

## Controls

- A source URL or document is mandatory.
- A document source must be active and belong to the same counterparty.
- Review actions use optimistic locking so stale updates receive a conflict.
- Creation, verification, rejection, and retirement write audit events.
- `dq-v5` flags unverified facts after a configurable grace period and verified facts after expiry.
- Fact values can be sensitive. Production deployment needs field-level authorization, encryption, retention rules, source licensing, and privacy review before real bank or ownership data is stored.

Facts add traceability to the assessment record. They do not replace official screening, independent document verification, deterministic policy, or accountable human judgment.
