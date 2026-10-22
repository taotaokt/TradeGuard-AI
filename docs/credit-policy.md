# Counterparty credit policies

M16 adds explicit commercial-credit controls to the assessment workflow. These policies are entered and approved by people; the synthetic model does not set a customer's limit.

## Lifecycle

1. An administrator or risk reviewer creates a draft policy for one counterparty and currency.
2. The draft records a semantic policy version, credit limit, maximum payment terms, minimum deposit, risk tier, rationale, effective date, and expiry.
3. Activation requires the expected record version and an approval rationale. It records the approver and time.
4. Activating a new version retires the previous active version for the same counterparty and currency. Historical policies remain queryable.
5. A draft or active policy may be retired with a rationale. Ordinary users cannot delete its history.

## Assessment calculation

For each linked counterparty with a current policy in the transaction currency, TradeGuard calculates:

```text
transaction exposure = requested credit exposure, when supplied
otherwise transaction exposure = amount × (1 − deposit percentage)

projected exposure = open recorded same-currency exposure + proposed exposure
```

Completed and policy-stopped transactions are excluded from existing exposure. Draft and review-stage
transactions are included conservatively until a fuller commitment and settlement lifecycle is added.

The assessment snapshots the policy and all three exposure values. It emits:

- `CREDIT_LIMIT_EXCEEDED` when projected exposure is above the approved limit;
- `PAYMENT_TERMS_EXCEED_POLICY` when requested terms are too long;
- `DEPOSIT_BELOW_POLICY` when the deposit is too small; and
- `COUNTERPARTY_CREDIT_RESTRICTED` when the active policy prohibits new exposure.

The first three signals route the transaction to risk review. A restricted policy produces a hard internal `STOP` before the model score is considered. A risk reviewer may confirm that same `STOP`, but cannot override it; the policy must be changed and the transaction reassessed. An expired active policy produces `DQ_CREDIT_POLICY_EXPIRED` under `dq-v5`.

## Limitations

The current exposure definition is deliberately transparent and does not model settlements, partial shipments, collateral, guarantees, insurance, foreign-exchange conversion, legal entity groups, or revolving facilities. Before family-business use, the company must define when exposure begins and ends, who can approve or override limits, which currencies can be aggregated, how overdue receivables are treated, and how policy evidence is retained. The included thresholds are fictional and must not be treated as validated credit advice.
