import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from decimal import Decimal

import pytest

from scripts.base_vol_adaptive_lp import BaseVolAdaptiveLP, BaseVolAdaptiveLPConfig
from scripts.uniswap_v3_full_cycle import UniV3FullCycleConfig


def _make_vol_strategy_for_test() -> BaseVolAdaptiveLP:
    strategy = BaseVolAdaptiveLP.__new__(BaseVolAdaptiveLP)
    strategy.w_min = 150
    strategy.w_max = 400
    strategy.sigma_0 = 0.8
    strategy.k = 200.0
    strategy.fallback_width_bps = 200
    strategy.log_with_clock = lambda *args, **kwargs: None
    return strategy


def _make_runtime_strategy_for_test() -> tuple[BaseVolAdaptiveLP, MagicMock, dict]:
    strategy = BaseVolAdaptiveLP.__new__(BaseVolAdaptiveLP)
    config = SimpleNamespace(
        trading_pair="WETH-USDC",
        network="base",
        entry_amount_eth=Decimal("0.1"),
        entry_amount_usdc=Decimal("200"),
        w_min=150,
        w_max=400,
        sigma_0=Decimal("0.8"),
        k=Decimal("200"),
        fallback_width_bps=200,
        max_position_pct=Decimal("50"),
        gas_token="ETH",
        min_gas_reserve=Decimal("0.02"),
        stop_loss_pct=Decimal("10"),
        analytics_output_path="logs/test_base_vol_adapter.jsonl",
        strategy_id="base_vol_adaptive_lp",
        check_interval=30,
        auto_open_position=True,
    )
    connector = MagicMock()
    balances = {
        "ETH": Decimal("0.05"),
        "WETH": Decimal("0.2"),
        "USDC": Decimal("1200"),
    }
    connector.get_balance.side_effect = lambda token: balances[token]
    connector.get_pool_address = AsyncMock(return_value="pool-1")
    connector.open_position = AsyncMock(return_value="open-1")
    connector.close_position = AsyncMock(return_value="close-1")
    connector.get_position_info = AsyncMock(
        return_value=SimpleNamespace(
            address="position-1",
            lower_price=Decimal("1800"),
            upper_price=Decimal("2200"),
            in_range=True,
            base_fee_amount=Decimal("0"),
            quote_fee_amount=Decimal("0"),
        )
    )

    strategy.config = config
    strategy.exchange = "uniswap/clmm/base"
    strategy.base_token = "WETH"
    strategy.quote_token = "USDC"
    strategy.connectors = {strategy.exchange: connector}
    strategy.w_min = int(config.w_min)
    strategy.w_max = int(config.w_max)
    strategy.sigma_0 = float(config.sigma_0)
    strategy.k = float(config.k)
    strategy.fallback_width_bps = int(config.fallback_width_bps)
    strategy.pool_info = SimpleNamespace(price=2000)
    strategy.position_info = None
    strategy.position_opened = False
    strategy.position_opening = False
    strategy.position_closing = False
    strategy.position_rebalancing = False
    strategy.entry_price = Decimal("2000")
    strategy.rebalance_count = 0
    strategy.last_adapter_event = None
    strategy.log_with_clock = lambda *args, **kwargs: None
    return strategy, connector, balances


def test_realized_vol_source_normal_path(monkeypatch):
    strategy = _make_vol_strategy_for_test()

    monkeypatch.setattr("scripts.market_indicators.get_realized_vol_7d", lambda: 120.0)
    width_bps = strategy._calculate_range_width()

    assert width_bps == 230  # 150 + 200 * (1.2 - 0.8)


def test_realized_vol_source_exception_path(monkeypatch):
    strategy = _make_vol_strategy_for_test()

    def _raise_error():
        raise RuntimeError("vol source failed")

    monkeypatch.setattr("scripts.market_indicators.get_realized_vol_7d", _raise_error)
    width_bps = strategy._calculate_range_width()

    assert width_bps == strategy.fallback_width_bps


def test_base_vol_risk_config_defaults_and_required_fields():
    cfg = BaseVolAdaptiveLPConfig()
    assert cfg.max_position_pct == Decimal("50")
    assert cfg.min_gas_reserve == Decimal("0.02")
    assert cfg.stop_loss_pct == Decimal("10")


def test_base_vol_risk_config_validation_rejects_invalid_values():
    with pytest.raises(ValueError):
        BaseVolAdaptiveLPConfig(max_position_pct=Decimal("60"))
    with pytest.raises(ValueError):
        BaseVolAdaptiveLPConfig(min_gas_reserve=Decimal("0"))
    with pytest.raises(ValueError):
        BaseVolAdaptiveLPConfig(stop_loss_pct=Decimal("0"))


def test_full_cycle_risk_config_validation_rejects_invalid_values():
    with pytest.raises(ValueError):
        UniV3FullCycleConfig(entry_quote_pct=Decimal("60"))
    with pytest.raises(ValueError):
        UniV3FullCycleConfig(entry_lower_buffer_bps=0)


def test_gas_reserve_insufficient_rejects_open_position():
    strategy, connector, balances = _make_runtime_strategy_for_test()
    balances["ETH"] = Decimal("0.001")

    asyncio.run(strategy._open_position())

    connector.open_position.assert_not_awaited()
    assert strategy.position_opened is False
    assert strategy.last_adapter_event["action"] == "hold"
    assert strategy.last_adapter_event["reason"] == "gas_reserve_insufficient"


def test_max_position_pct_total_exposure_blocks_open():
    strategy, connector, balances = _make_runtime_strategy_for_test()
    strategy.config.entry_amount_eth = Decimal("0.2")
    strategy.config.entry_amount_usdc = Decimal("200")
    balances["WETH"] = Decimal("0")
    balances["USDC"] = Decimal("1000")

    asyncio.run(strategy._open_position())

    connector.open_position.assert_not_awaited()
    assert strategy.last_adapter_event["reason"] == "max_position_pct_exceeded"


def test_stop_loss_trigger_executes_close_path():
    strategy, connector, _ = _make_runtime_strategy_for_test()
    strategy.position_opened = True
    strategy.position_info = SimpleNamespace(
        address="position-1",
        lower_price=Decimal("1500"),
        upper_price=Decimal("2500"),
        in_range=True,
        base_fee_amount=Decimal("0"),
        quote_fee_amount=Decimal("0"),
    )

    async def fake_fetch_pool_info():
        strategy.pool_info = SimpleNamespace(price=1700)

    strategy._fetch_pool_info = fake_fetch_pool_info
    connector.get_position_info = AsyncMock(return_value=strategy.position_info)

    asyncio.run(strategy._monitor_position())

    connector.close_position.assert_awaited_once()
    assert strategy.position_opened is False
    assert strategy.last_adapter_event["action"] == "close"
    assert strategy.last_adapter_event["reason"] == "stop_loss"


def test_adapter_field_completeness():
    strategy, _, _ = _make_runtime_strategy_for_test()
    strategy.position_info = SimpleNamespace(
        lower_price=Decimal("1800"),
        upper_price=Decimal("2200"),
        in_range=True,
        base_fee_amount=Decimal("0.001"),
        quote_fee_amount=Decimal("1.2"),
    )
    event = strategy._build_adapter_event(
        action="open",
        reason="entry_opened",
        price=Decimal("2000"),
        range_lower=Decimal("1800"),
        range_upper=Decimal("2200"),
        in_range=True,
        gas_cost=Decimal("0.01"),
    )
    required_fields = {
        "strategy_id",
        "timestamp",
        "action",
        "reason",
        "price",
        "range_lower",
        "range_upper",
        "in_range",
        "fees_collected",
        "estimated_il_pct",
        "gas_cost",
    }
    assert required_fields.issubset(event.keys())


def test_adapter_output_path_without_dirname_no_makedirs(monkeypatch, tmp_path):
    strategy, _, _ = _make_runtime_strategy_for_test()
    strategy.config.analytics_output_path = "adapter_events.jsonl"

    monkeypatch.setattr("scripts.base_vol_adaptive_lp.os.getcwd", lambda: str(tmp_path))

    def _forbid_makedirs(*args, **kwargs):
        raise AssertionError("os.makedirs should not be called for filename-only analytics_output_path")

    monkeypatch.setattr("scripts.base_vol_adaptive_lp.os.makedirs", _forbid_makedirs)

    strategy._emit_adapter_event(
        action="hold",
        reason="unit_test",
        price=Decimal("2000"),
        in_range=None,
        gas_cost=None,
    )

    assert (tmp_path / "adapter_events.jsonl").exists()
