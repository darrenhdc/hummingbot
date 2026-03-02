# Hummingbot Migration Spec - Technical Specification

## 1. Scope

This spec defines how to migrate core trading logic from the baseline project:

- `/Users/darrencui/defi_labs/quick-start-uniswap-v3`

to Hummingbot:

- `/Users/darrencui/hummingbot`

while preserving behavior parity for Uniswap v3 LP strategy operations.

## 2. Architecture

## 2.1 Runtime Model

- Single codebase (`hummingbot`)
- Multi-instance execution:
  - Instance A: Uniswap v3 LP strategy
  - Instance B: Hyperliquid perp strategy
- Isolated runtime artifacts per instance:
  - config file
  - log file
  - state file namespace

## 2.2 Strategy Layer

Target strategy files:

- `scripts/uniswap_v3_full_cycle.py` (primary FSM migration)
- `scripts/base_vol_adaptive_lp.py` (vol-adaptive behavior)

Required behavior:

- phase-based decisioning:
  - idle
  - entry
  - await_breakeven_open
  - breakeven
- deterministic transitions
- explicit recovery path for invalid/unknown state

## 2.3 Risk Control Layer

Required controls:

- Position size cap:
  - hard cap: no more than 50% of total capital per strategy
- Gas reserve gate:
  - reject open/rebalance if reserve below configured threshold
- Stop-loss:
  - mandatory and configurable by position bucket
- OOR fail-safe:
  - alert and close/review when out-of-range duration breaches threshold

## 2.4 Data Contract Layer

Phase 1 contract (minimal):

- strategy_id
- timestamp
- action (open/close/rebalance/hold)
- reason
- price
- range_lower
- range_upper
- in_range
- fees_collected
- estimated_il_pct
- gas_used/gas_cost

Purpose:

- Keep existing dashboard/portfolio/subgraph services usable via adapter.

## 3. Configuration Specification

Config classes must include:

- network
- trading_pair
- position sizing fields
- range configuration fields
- stop-loss fields
- check_interval
- optional auto_open_position

Config constraints:

- reject invalid percentages
- reject unsafe size above cap
- validate compatible connector/network pair

## 4. Test Specification

## 4.1 Unit Tests

- state transition correctness
- boundary handling
- risk guard checks
- config validation

## 4.2 Integration Tests

- open -> monitor -> close loop
- out-of-range -> rebalance loop
- watcher restart and state recovery

## 4.3 Operational Tests

- gateway unavailable
- tx timeout
- insufficient gas
- stale state cleanup

## 5. Acceptance Criteria

- Core LP behavior matches baseline intent with no critical regression.
- No unresolved deadlock/lockfile failure in 24h run.
- Risk checks are enforced before capital deployment.
- External analytics adapter receives required fields correctly.

## 6. Non-Goals

- Full UI migration into Hummingbot in phase 1
- New chain/DEX connector development (e.g., SUI, Magma Finance)

## 7. Security Requirements

- No plaintext private keys in repo/config files.
- RPC credentials stored only in env/config secrets.
- Rotate any leaked keys immediately.

