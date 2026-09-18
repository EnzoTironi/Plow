# LedgerOS

A finance operations agent built on eve. The first vertical slice is invoice-to-cash exception resolution.

## Current slice

- tenant-scoped invoice and payment schemas
- deterministic reconciliation in integer minor units
- stable idempotency keys for collection actions
- eve agent with strict instructions
- read-only reconciliation tool
- human-approved proposal tool with no external side effect yet
- weekday overdue scan schedule
- tests for paid, partial, cross-tenant, and ambiguous cases

## Run

```sh
npm install
npm test
npm run typecheck
npm run build
```

`eve` is still preview software. Keep its APIs behind the `agent/` boundary and the finance domain independent of it.

## Safety boundary

The model may interpret evidence and propose a typed action. It does not own financial truth, authorization, tenant identity, money arithmetic, or external writes. Payment initiation, journal posting, bank-detail changes, and outbound communication remain disabled until their adapters have provider-level idempotency, audit records, policy checks, and approval gates.
