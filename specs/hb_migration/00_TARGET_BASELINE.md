# Hummingbot Migration Spec - Target Baseline

## Objective

Build the next version directly on top of the Hummingbot repo, while preserving the proven strategy logic from the existing self-implemented Uniswap v3 LP system.

## Source-of-Truth Baseline Project

Primary reference project:

- `/Users/darrencui/defi_labs/quick-start-uniswap-v3`

Primary baseline modules:

- Strategy FSM and decision rules:
  - `strategies/strategy_001_full_cycle/strategy.py`
  - `strategies/strategy_000_vol_adaptive/strategy.py`
- Runtime execution and position lifecycle:
  - `src/bot.py`
  - `src/watcher.py`
- Strategy parameters and mode switching:
  - `config/strategy.yaml`
- Existing observability and metrics expectations:
  - `web/api.py`
  - `web/static/*`
  - `src/subgraph_client.py`

## New Target Project

Target implementation repo:

- `/Users/darrencui/hummingbot`

Target principle:

- Migrate core trading logic to Hummingbot strategy scripts and connectors.
- Keep existing dashboard/portfolio/subgraph services as external modules in phase 1.
- Integrate data contracts incrementally rather than big-bang rewrite.

## In-Scope (Phase 1)

- Uniswap v3 LP core lifecycle:
  - open, monitor, close, rebalance
- FSM-equivalent logic for strategy_001_full_cycle
- Volatility-adaptive logic for strategy_000 (or equivalent)
- Production-safe risk controls:
  - max position sizing cap
  - gas reserve checks
  - stop-loss / fail-safe behavior
- Multi-instance runtime isolation for:
  - Uniswap LP strategy
  - Hyperliquid perp strategy

## Out-of-Scope (Phase 1)

- Full dashboard rewrite inside Hummingbot
- Full portfolio backend rewrite
- SUI connector implementation
- Magma Finance connector implementation

## Success Criteria

- Hummingbot strategies can reproduce baseline lifecycle behavior for LP core logic.
- Strategy can run continuously without state lock/deadloop failure modes seen in baseline pitfalls.
- Existing external analytics stack can consume strategy outputs with minimal adapter layer.

