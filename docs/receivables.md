# Trade receivables and payments

M17 connects approved trade exposure with actual collection activity. The ledger is intentionally small: one transaction can have one receivable, and each receipt is an immutable payment record.

## Workflow

1. Create a transaction with a linked counterparty.
2. Open its receivable through `POST /api/transactions/{id}/receivable` with an invoice reference, amount, issue time, and due time.
3. View aging and history through `GET /api/receivables` or `GET /api/transactions/{id}/receivable`.
4. Record each receipt through `POST /api/receivables/{id}/payments` using the latest receivable version.
5. A partial payment changes the status to `partially_paid` and reduces the outstanding balance.
6. The final payment changes the status to `paid`, completes the transaction, and creates a `paid_on_time` or `delayed` outcome when no outcome already exists.

Every create and payment operation produces an audit event. Payment references are unique, overpayments are rejected, and optimistic locking prevents two users from silently applying changes to the same balance version.

## Exposure and aging

An assessment uses the current outstanding receivable balance for an invoice-backed open trade. If an open trade has no receivable, TradeGuard continues to use the transparent unsecured-exposure estimate. Values are only combined inside the same policy currency.

The `aging_status` response field is calculated at read time:

- `open` before the due time with no payments;
- `partially_paid` before the due time after a partial receipt;
- `overdue` after the due time while any balance remains; or
- `paid` after full settlement.

The `dq-v6` scan creates `DQ_RECEIVABLE_OVERDUE` for each past-due balance and automatically resolves it after settlement. A final receipt at least 30 days after the due date also creates the existing adverse-payment-outcome alert and notification record.

## Boundaries before real use

The current ledger does not support multiple invoices per transaction, credit notes, refunds, write-offs, disputed allocations, bank-statement matching, multi-currency settlement, or accounting-system synchronization. A production family-business rollout should define approval authority, invoice and payment identifiers, accounting reconciliation, timezone rules, amendment history, and access to bank data before importing real records.
