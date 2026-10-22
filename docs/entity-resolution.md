# Counterparty entity resolution

M14 helps prevent one real company from being represented by several disconnected counterparty records. Fragmented records can hide prior screening results, exposure, outcomes, and reviewer decisions.

## Candidate generation

On creation, a counterparty is compared with non-archived records using:

- Unicode-normalized legal names and aliases;
- configurable name-similarity thresholds, stricter across jurisdictions;
- jurisdiction agreement;
- case-insensitive registration-number agreement; and
- normalized website-domain agreement.

The candidate stores the similarity score, matched name, and every supporting signal. A strong match creates `review_required`; it does not automatically merge, archive, or reject either company.

## Human resolution

A risk reviewer may classify a candidate as `not_duplicate` or `confirmed_duplicate` with a rationale and expected version. Clearing all candidates returns the new record to `clear`. Confirming a duplicate sets its canonical counterparty reference while retaining both records and their historical activity.

Pending and confirmed concerns add `COUNTERPARTY_DUPLICATE_REVIEW` to linked assessment reasons, set the identity/KYB dimension to `duplicate_review`, and route the assessment to risk review. They also produce a `DQ_COUNTERPARTY_DUPLICATE_REVIEW` issue under the current `dq-v4` ruleset.

## Boundaries

This workflow is deterministic entity-resolution support, not authoritative corporate identity verification. Production use should add approved registry identifiers, address and ownership evidence, country-specific normalization, transliteration review, threshold validation, and a governed merge or record-linking procedure.
