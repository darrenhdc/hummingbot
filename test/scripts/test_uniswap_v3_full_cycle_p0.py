import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.gateway.common_types import ConnectorType
from scripts.uniswap_v3_full_cycle import StrategyState, UniV3FullCycle


def _make_strategy():
    strategy = UniV3FullCycle.__new__(UniV3FullCycle)
    config = SimpleNamespace(
        trading_pair="WETH-USDC",
        gas_token="ETH",
        min_gas_reserve=Decimal("0.02"),
        order_max_pending_seconds=10,
        phase_stuck_timeout_sec=10,
        entry_base_pct=Decimal("0"),
        entry_quote_pct=Decimal("100"),
        breakeven_base_pct=Decimal("100"),
        breakeven_quote_pct=Decimal("0"),
        slippage_pct=None,
        entry_price_min=Decimal("1000"),
        entry_price_max=Decimal("5000"),
        entry_width_bps=300,
        entry_lower_buffer_bps=30,
        breakeven_target_quote=Decimal("100"),
        breakeven_min_bps_above_entry_lower=1,
    )
    connector = MagicMock()
    balances = {
        "ETH": Decimal("1"),
        "WETH": Decimal("1"),
        "USDC": Decimal("1000"),
    }
    connector.get_balance.side_effect = lambda token: balances[token]
    connector.add_liquidity.return_value = "open-1"
    connector.remove_liquidity.return_value = "close-1"

    strategy.config = config
    strategy.exchange = "uniswap/clmm"
    strategy.connector_type = ConnectorType.CLMM
    strategy.base_token = "WETH"
    strategy.quote_token = "USDC"
    strategy.connectors = {strategy.exchange: connector}
    strategy.state = StrategyState()
    strategy.pool_info = None
    strategy.position_info = None
    strategy.position_opened = False
    strategy.position_opening = False
    strategy.position_closing = False
    strategy.open_order_id = None
    strategy.close_order_id = None
    strategy.pending_close_reason = None
    strategy.pending_phase_after_close = None
    strategy.phase_entered_at = datetime.now() - timedelta(seconds=60)
    strategy.open_order_created_at = None
    strategy.close_order_created_at = None
    strategy.last_price = None
    strategy.last_price_update = None
    strategy._tick_task = None
    return strategy, connector, balances


def test_unknown_phase_resets_to_idle():
    strategy, _, _ = _make_strategy()
    strategy.state.phase = "bad_phase"

    assert strategy._ensure_known_phase() is False
    assert strategy.state.phase == "idle"


def test_pool_liquidity_zero_guard_skips_handlers():
    strategy, _, _ = _make_strategy()

    async def fake_fetch_pool_info():
        strategy.pool_info = SimpleNamespace(price=2000, base_token_amount=0, quote_token_amount=0)

    strategy._fetch_pool_info = fake_fetch_pool_info
    strategy._handle_no_position = AsyncMock()
    strategy._handle_position = AsyncMock()

    asyncio.run(strategy._tick_async())

    strategy._handle_no_position.assert_not_awaited()
    strategy._handle_position.assert_not_awaited()


def test_open_entry_blocked_when_gas_reserve_insufficient():
    strategy, connector, balances = _make_strategy()
    balances["ETH"] = Decimal("0.001")
    strategy.config.min_gas_reserve = Decimal("0.01")

    asyncio.run(strategy._open_entry(Decimal("2000")))

    connector.add_liquidity.assert_not_called()
    assert strategy.position_opening is False
    assert strategy.state.phase == "idle"


def test_open_entry_succeeds_with_enough_gas_reserve():
    strategy, connector, balances = _make_strategy()
    balances["ETH"] = Decimal("0.05")
    strategy.config.min_gas_reserve = Decimal("0.01")

    asyncio.run(strategy._open_entry(Decimal("2000")))

    connector.add_liquidity.assert_called_once()
    assert strategy.position_opening is True
    assert strategy.state.phase == "entry"


def test_phase_stuck_timeout_resets_to_idle():
    strategy, _, _ = _make_strategy()
    strategy.state.phase = "entry"
    strategy.position_opened = False
    strategy.position_opening = False
    strategy.config.phase_stuck_timeout_sec = 1
    strategy.phase_entered_at = datetime.now() - timedelta(seconds=5)

    assert strategy._ensure_state_consistency() is False
    assert strategy.state.phase == "idle"


def test_open_order_pending_timeout_resets_to_idle():
    strategy, _, _ = _make_strategy()
    strategy.state.phase = "entry"
    strategy.position_opening = True
    strategy.open_order_id = "open-1"
    strategy.open_order_created_at = datetime.now() - timedelta(seconds=5)
    strategy.config.order_max_pending_seconds = 1

    assert strategy._ensure_state_consistency() is False
    assert strategy.position_opening is False
    assert strategy.open_order_id is None
    assert strategy.state.phase == "idle"


def test_on_tick_recovers_stale_pending_open():
    strategy, _, _ = _make_strategy()
    strategy.state.phase = "entry"
    strategy.position_opening = True
    strategy.open_order_id = "open-1"
    strategy.open_order_created_at = datetime.now() - timedelta(seconds=5)
    strategy.config.order_max_pending_seconds = 1

    strategy.on_tick()

    assert strategy.position_opening is False
    assert strategy.open_order_id is None
    assert strategy.state.phase == "idle"
