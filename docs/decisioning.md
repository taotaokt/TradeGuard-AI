# Decisioning workflow

TradeGuard currently runs an assessment synchronously so the workflow is easy to inspect and test.
Each assessment stores an immutable transaction snapshot, screening-version snapshot, rule version,
rule checksum, model version, feature snapshot, calibrated prediction, step outputs, triggered rules,
and an automatic recommendation.

## Step order

1. Validate required transaction information.
2. Read the screening state of linked counterparties and active list versions.
3. Evaluate every rule in `config/rules/v1.json`.
4. Verify and load the registered champion artifact, extract the fixed feature schema, estimate the
   calibrated probability, and record confidence and policy-oriented reason codes.
5. Apply decision precedence and create a review case when needed.

## Decision precedence

1. A confirmed compliance concern produces `COMPLIANCE_HOLD`.
2. A critical deterministic rule produces a hard-stop `REQUEST_INFORMATION` result.
3. Other missing or inconsistent information produces `REQUEST_INFORMATION`.
4. Incomplete screening, possible matches, or manual-review rules produce `REFER`.
5. An unavailable model, an out-of-range input, or a non-low commercial-risk band produces `REFER`.
6. A transaction with no triggered issue and a low model band produces `APPROVE`.

A hard stop cannot be changed through the review endpoint. The source concern must be corrected or
resolved first, followed by a new assessment version. This prevents a favorable future ML score or a
routine reviewer action from silently cancelling a compliance decision.

## Model safeguards

The application verifies the artifact SHA-256 digest before deserialization and requires the manifest
feature order to match the application schema exactly. It stores the data checksum, runtime versions,
metrics, input feature snapshot, probability, risk band, confidence, and uncertainty reason. Inputs
outside a recorded training range are not extrapolated as high-confidence decisions. Returned feature
flags are review aids, not causal explanations.

The included model uses generated data only. It must not be used for real lending, trade limits, or
credit denial without a separate data-governance, legal, validation, and approval process.

## Manual review

Risk and compliance queues are separated by the `required_role` field. Reviewers must provide a
rationale. `APPROVE_WITH_CONDITIONS` also requires at least one written condition. The automatic and
final recommendations are both retained, and a different final result is marked as an override. Each
condition becomes a due-dated record owned by a reviewer role. It can be fulfilled only with active
transaction evidence, waived with authority and rationale, or reopened with optimistic version checks.

## Demonstration thresholds

The current payment-term and exposure thresholds are unvalidated portfolio-demo values. They live in
the versioned JSON configuration so that they are visible and reproducible, but they must not be
presented as approved family-business policy until reviewed against real trade history and risk limits.
