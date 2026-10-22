# Portfolio analytics and stress testing

TradeGuard's portfolio layer is an analytical view over recorded transactions. It does not approve credit, set a customer limit, or change a prior decision.

## Exposure summary

`GET /api/portfolio/summary` uses each open transaction's requested credit exposure, falling back to transaction amount when no requested exposure was supplied. It selects the latest available prediction for each transaction and returns:

- open, assessed, and unscored transaction counts;
- exposure by currency;
- exposure by latest risk band;
- exposure by destination country; and
- observed outcome and recorded-loss summaries.

Every exposure bucket includes its currency. TradeGuard intentionally does not add USD, CNY, EUR, or other currencies together because the project has no governed exchange-rate source or valuation date.

## Saved stress tests

Risk reviewers can submit a scenario to `POST /api/portfolio/stress-tests` with:

- a portfolio-wide adverse-probability multiplier;
- an exposure-growth percentage;
- loss given default;
- a fallback probability for unscored transactions; and
- optional destination countries with an additional probability shock.

For each transaction, the demonstration calculates:

```text
baseline expected loss = exposure × baseline probability × loss given default
stressed expected loss = stressed exposure × stressed probability × loss given default
```

Probabilities are capped at 1.0. Results remain separated by currency and include the baseline exposure, stressed exposure, baseline expected loss, stressed expected loss, and delta.

Each saved record contains the scenario rationale, normalized parameters, exact open-transaction snapshot, result, actor, and timestamp. Creating a stress test does not modify transaction status, assessment versions, model predictions, decisions, or review cases.

## Limitations

The calculation is a transparent sensitivity analysis, not IFRS 9, CECL, regulatory capital, or a validated economic scenario model. Production use would require governed exchange rates, exposure-at-default rules, collateral and recovery data, maturity, correlated scenarios, macroeconomic calibration, validation, approvals, and controlled reporting.
