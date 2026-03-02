# Hummingbot Migration Spec - Roadmap

## Delivery Strategy

Use a phased migration:

1. move execution-critical logic first
2. keep non-critical services stable
3. replace components only after parity is proven

## Phase Plan

## Phase 0 - Setup and Baseline Freeze (0.5-1 day)

- Lock baseline behavior snapshots from:
  - `/Users/darrencui/defi_labs/quick-start-uniswap-v3`
- Define feature parity matrix:
  - strategy triggers
  - state transitions
  - order lifecycle
  - risk checks
- Prepare runtime config separation in Hummingbot:
  - LP instance config
  - Hyperliquid instance config

Exit criteria:

- Baseline feature list frozen
- Migration acceptance checklist approved

## Phase 1 - Core LP Strategy Parity (3-5 days)

- Implement/mature Hummingbot LP strategy script based on baseline FSM
- Add explicit guards:
  - gas reserve check
  - position size cap (< 50% total capital)
  - stop-loss behavior
  - state recovery behavior
- Validate commands and lifecycle:
  - open
  - monitor
  - close
  - rebalance

Exit criteria:

- Strategy runs with deterministic state transitions
- No blocking error in 24h paper/small-cap run

## Phase 2 - Hyperliquid and LP Co-Run (1-2 days)

- Run Hyperliquid perp and LP in isolated processes
- Verify no shared-state interference:
  - config isolation
  - log isolation
  - wallet/risk isolation

Exit criteria:

- Both strategies run concurrently with stable heartbeat and no state collision

## Phase 3 - Analytics Adapter Layer (3-5 days)

- Create minimal adapter from Hummingbot logs/state to existing analytics schema
- Keep old dashboard/portfolio/subgraph stack active
- Backfill required fields for:
  - pnl
  - fees
  - gas
  - position status

Exit criteria:

- Existing dashboards can read migrated strategy output
- Key metrics remain consistent with baseline tolerance

## Phase 4 - Hardening and Production SOP (2-3 days)

- Runbook for start/stop/recovery/emergency close
- Failure drills:
  - gateway disconnect
  - tx timeout
  - out-of-range long duration
- Final go-live checklist

Exit criteria:

- Operational checklist signed off
- Small-cap production trial completed successfully

## Timeline Summary

- Fast track (core only): 3-5 days
- Recommended stable migration: 2-3 weeks

## Decision Gates

- Gate A (after Phase 1): core parity good enough?
- Gate B (after Phase 3): analytics compatibility good enough?
- Gate C (after Phase 4): production readiness approved?

