# Approval-condition workflow

M13 turns `APPROVE_WITH_CONDITIONS` from a report-only statement into an operational control. Conditions remain linked to the immutable assessment and decision that created them.

## Workflow

1. A risk or compliance reviewer records an approval with one or more conditions.
2. TradeGuard creates a sequenced record for each condition, using a 30-day deadline by default.
3. The reviewer may choose a business, risk, or compliance owner role and assign an eligible user through the API.
4. The owner uploads evidence to the assessed transaction.
5. The owner fulfills the condition by referencing that active document and recording a rationale.
6. An authorized owner may waive a condition with a rationale or reopen a fulfilled or waived condition.
7. The current status and evidence reference appear in the assessment PDF. Open overdue conditions become data-quality findings.

## Concurrency and audit behavior

Every action supplies `expected_version`. A stale action returns HTTP 409 instead of overwriting another reviewer's work. Assignment, fulfillment, waiver, and reopening write immutable audit events with the actor, prior and resulting state, rationale, and evidence reference.

## Boundaries

The workflow proves that a document was attached and linked; it does not verify the document's legal validity, authenticity, signature, or sufficiency. Production use requires an approved condition taxonomy, escalation policy, evidence-retention rules, and legal or compliance review for material obligations.
