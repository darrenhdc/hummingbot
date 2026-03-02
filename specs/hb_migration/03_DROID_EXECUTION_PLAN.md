# Hummingbot Migration Spec - Droid Execution Plan

## Execution Model

This plan is written for Droid (Factory.ai) to execute in strict spec-driven mode.

Mandatory reference baseline:

- `/Users/darrencui/defi_labs/quick-start-uniswap-v3`

Mandatory target repo:

- `/Users/darrencui/hummingbot`

## Global Rules for Droid

1. Do not change baseline repo behavior directly.
2. Implement in target repo only.
3. Keep commits atomic and phase-scoped.
4. Run tests/checks before each handoff.
5. Never bypass risk controls in strategy code.

## Work Packages

## WP-1 Baseline Mapping

Inputs:

- `00_TARGET_BASELINE.md`
- baseline strategy files and bot lifecycle

Tasks:

- Build feature parity checklist (`docs/migration_parity_checklist.md`)
- Map each baseline decision path to target script method

Deliverable:

- parity checklist with status: mapped/unmapped

## WP-2 LP FSM Parity Implementation

Inputs:

- `02_TECH_SPEC.md`
- target script: `scripts/uniswap_v3_full_cycle.py`

Tasks:

- implement/verify FSM phases
- add state recovery path
- ensure deterministic phase transitions

Deliverable:

- updated strategy script + tests

## WP-3 Risk Guard Enforcement

Tasks:

- add pre-trade gas reserve check
- add position-size cap enforcement
- verify stop-loss behavior

Deliverable:

- guard checks covered by unit tests

## WP-4 Dual-Instance Runtime Isolation

Tasks:

- document and implement two isolated runtime profiles:
  - LP profile
  - Hyperliquid profile
- separate logs and state namespaces

Deliverable:

- `docs/runbooks/dual_instance_runbook.md`

## WP-5 Analytics Adapter (Minimal)

Tasks:

- produce normalized strategy event output schema
- create adapter interface doc for existing dashboard stack

Deliverable:

- `docs/migration_analytics_adapter.md`

## Handoff Checklist Per WP

- Code changes committed
- Tests executed and passed
- Diff summary written
- Known risks listed
- Rollback notes included

## Suggested Commit Sequence

1. `spec: add migration parity checklist`
2. `feat: migrate lp fsm core logic`
3. `feat: enforce gas and position risk guards`
4. `chore: add dual-instance runtime runbook`
5. `feat: add analytics adapter contract docs`

## Quality Gate

Droid must stop and report if any of the following occurs:

- state transition ambiguity
- conflicting config semantics
- missing risk guard coverage
- mismatch between implemented behavior and baseline intent

