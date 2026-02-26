import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.common_types import ConnectorType, get_connector_type
from hummingbot.connector.gateway.gateway_lp import CLMMPoolInfo, CLMMPositionInfo
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class UniV3FullCycleConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    connector: str = Field(
        "uniswap/clmm",
        json_schema_extra={
            "prompt": "CLMM connector in format 'name/type' (e.g. uniswap/clmm)",
            "prompt_on_new": True,
        },
    )
    trading_pair: str = Field(
        "WETH-USDC",
        json_schema_extra={"prompt": "Trading pair (e.g. WETH-USDC)", "prompt_on_new": True},
    )
    entry_price_min: Decimal = Field(
        Decimal("2700"),
        json_schema_extra={"prompt": "Entry price min (quote per base)", "prompt_on_new": True},
    )
    entry_price_max: Decimal = Field(
        Decimal("2900"),
        json_schema_extra={"prompt": "Entry price max (quote per base)", "prompt_on_new": True},
    )
    entry_width_bps: int = Field(
        300,
        json_schema_extra={"prompt": "Entry width bps (e.g. 300 = 3%)", "prompt_on_new": True},
    )
    entry_lower_buffer_bps: int = Field(
        30,
        json_schema_extra={"prompt": "Entry lower buffer bps (e.g. 30 = 0.3%)", "prompt_on_new": True},
    )
    breakeven_target_quote: Decimal = Field(
        Decimal("100"),
        json_schema_extra={"prompt": "Breakeven target in quote token", "prompt_on_new": True},
    )
    entry_base_pct: Decimal = Field(
        Decimal("0"),
        json_schema_extra={"prompt": "Entry: use % of base token balance", "prompt_on_new": True},
    )
    entry_quote_pct: Decimal = Field(
        Decimal("100"),
        json_schema_extra={"prompt": "Entry: use % of quote token balance", "prompt_on_new": True},
    )
    breakeven_base_pct: Decimal = Field(
        Decimal("100"),
        json_schema_extra={"prompt": "Breakeven: use % of base token balance", "prompt_on_new": True},
    )
    breakeven_quote_pct: Decimal = Field(
        Decimal("0"),
        json_schema_extra={"prompt": "Breakeven: use % of quote token balance", "prompt_on_new": True},
    )
    breakeven_min_bps_above_entry_lower: int = Field(
        1,
        json_schema_extra={"prompt": "Min bps above entry lower for breakeven clamp", "prompt_on_new": True},
    )
    slippage_pct: Optional[Decimal] = Field(
        None,
        json_schema_extra={"prompt": "Max slippage % (optional)", "prompt_on_new": False},
    )
    check_interval: int = Field(
        10,
        json_schema_extra={"prompt": "Check interval (seconds)", "prompt_on_new": False},
    )
    adopt_existing_position: bool = Field(
        False,
        json_schema_extra={"prompt": "Adopt existing CLMM position if found?", "prompt_on_new": True},
    )


@dataclass
class StrategyState:
    phase: str = "idle"  # idle | entry | await_breakeven_open | breakeven
    entry_lower_price: Optional[Decimal] = None
    entry_upper_price: Optional[Decimal] = None
    breakeven_price: Optional[Decimal] = None


class UniV3FullCycle(ScriptStrategyBase):
    """
    Uniswap v3 CLMM full-cycle strategy adapted from your Strategy001 logic.

    Phases:
      - idle: wait for price within entry range
      - entry: open range; close on upper or lower buffer breach
      - await_breakeven_open: after lower breach, compute breakeven and open new range
      - breakeven: close once price recovers to breakeven
    """

    @classmethod
    def init_markets(cls, config: UniV3FullCycleConfig):
        cls.markets = {config.connector: {config.trading_pair}}

    def __init__(self, connectors: Dict[str, ConnectorBase], config: UniV3FullCycleConfig):
        super().__init__(connectors)
        self.config = config
        self.exchange = config.connector
        self.connector_type = get_connector_type(config.connector)
        self.base_token, self.quote_token = config.trading_pair.split("-")

        self.state = StrategyState()
        self.pool_info: Optional[CLMMPoolInfo] = None
        self.position_info: Optional[CLMMPositionInfo] = None

        self.position_opened = False
        self.position_opening = False
        self.position_closing = False
        self.open_order_id: Optional[str] = None
        self.close_order_id: Optional[str] = None
        self.pending_close_reason: Optional[str] = None
        self.pending_phase_after_close: Optional[str] = None

        self.last_check_time: Optional[datetime] = None
        self.last_price: Optional[Decimal] = None
        self.last_price_update: Optional[datetime] = None
        self._tick_task = None

        if self.connector_type != ConnectorType.CLMM:
            self.log_with_clock(logging.ERROR, f"{self.exchange} is not a CLMM connector.")

        safe_ensure_future(self._startup())

    async def _startup(self):
        await asyncio.sleep(3)
        await self._fetch_pool_info()
        if self.config.adopt_existing_position:
            await self._try_adopt_existing_position()

    def on_tick(self):
        if self.connector_type != ConnectorType.CLMM:
            return
        if self.position_opening or self.position_closing:
            return
        if self._tick_task is not None and not self._tick_task.done():
            return
        if not self._should_check():
            return
        self._tick_task = safe_ensure_future(self._tick_async())

    def _should_check(self) -> bool:
        now = datetime.now()
        if self.last_check_time is None:
            self.last_check_time = now
            return True
        if (now - self.last_check_time).total_seconds() >= self.config.check_interval:
            self.last_check_time = now
            return True
        return False

    async def _tick_async(self):
        await self._fetch_pool_info()
        if not self.pool_info:
            return

        price = Decimal(str(self.pool_info.price))
        self.last_price = price
        self.last_price_update = datetime.now()

        if self.position_opened:
            await self._refresh_position_info()
            await self._handle_position(price)
        else:
            await self._handle_no_position(price)

    async def _fetch_pool_info(self):
        try:
            self.pool_info = await self.connectors[self.exchange].get_pool_info(
                trading_pair=self.config.trading_pair
            )
        except Exception as e:
            self.logger().error(f"Error fetching pool info: {e}")
            self.pool_info = None

    async def _get_pool_address(self) -> Optional[str]:
        try:
            return await self.connectors[self.exchange].get_pool_address(self.config.trading_pair)
        except Exception as e:
            self.logger().error(f"Error fetching pool address: {e}")
            return None

    async def _try_adopt_existing_position(self):
        try:
            pool_address = await self._get_pool_address()
            if not pool_address:
                return
            positions = await self.connectors[self.exchange].get_user_positions(pool_address=pool_address)
            if positions:
                self.position_info = positions[-1]
                self.position_opened = True
                self.state.phase = "entry"
                self.state.entry_lower_price = Decimal(str(self.position_info.lower_price))
                self.state.entry_upper_price = Decimal(str(self.position_info.upper_price))
                self.logger().info(f"Adopted existing CLMM position: {self.position_info.address}")
        except Exception as e:
            self.logger().error(f"Error adopting existing position: {e}")

    async def _refresh_position_info(self):
        if not self.position_info:
            return
        try:
            self.position_info = await self.connectors[self.exchange].get_position_info(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address,
            )
        except Exception as e:
            self.logger().error(f"Error refreshing position info: {e}")

    async def _handle_no_position(self, price: Decimal):
        phase = self.state.phase
        if phase in ("idle", ""):
            if self._price_in_entry_range(price):
                await self._open_entry(price)
            return

        if phase == "await_breakeven_open":
            entry_lower = self.state.entry_lower_price
            breakeven_price = self.state.breakeven_price
            if entry_lower is None or breakeven_price is None:
                self.logger().warning("Missing breakeven params; resetting to idle.")
                self.state = StrategyState()
                return
            if price > entry_lower:
                self.logger().info("Price recovered above entry lower; reset to idle.")
                self.state = StrategyState()
                return
            await self._open_breakeven(entry_lower, breakeven_price)
            return

    async def _handle_position(self, price: Decimal):
        phase = self.state.phase
        if phase == "entry":
            entry_lower, entry_upper = self._entry_bounds_from_state(price)
            if price >= entry_upper:
                await self._close_position(
                    reason="upper",
                    next_phase="idle",
                )
                return

            trigger_price = entry_lower * (Decimal("1") - self._entry_lower_buffer())
            if price <= trigger_price:
                await self._close_position(
                    reason="lower",
                    next_phase="await_breakeven_open",
                )
            return

        if phase == "breakeven":
            breakeven_price = self.state.breakeven_price
            if breakeven_price is None:
                self.logger().warning("Missing breakeven price; resetting to idle.")
                self.state = StrategyState()
                return
            if price >= breakeven_price:
                await self._close_position(reason="breakeven", next_phase="idle")
            return

    async def _open_entry(self, price: Decimal):
        if self.position_opening or self.position_opened:
            return
        lower_price, upper_price = self._build_entry_bounds(price)
        base_amount, quote_amount = self._wallet_amounts(
            self.config.entry_base_pct, self.config.entry_quote_pct
        )
        if base_amount <= 0 and quote_amount <= 0:
            self.logger().warning("No available balance for entry.")
            return
        self.position_opening = True
        order_id = self.connectors[self.exchange].add_liquidity(
            trading_pair=self.config.trading_pair,
            price=float(price),
            lower_price=float(lower_price),
            upper_price=float(upper_price),
            base_token_amount=float(base_amount) if base_amount > 0 else None,
            quote_token_amount=float(quote_amount) if quote_amount > 0 else None,
            slippage_pct=float(self.config.slippage_pct) if self.config.slippage_pct is not None else None,
        )
        self.open_order_id = order_id
        self.state.phase = "entry"
        self.state.entry_lower_price = lower_price
        self.state.entry_upper_price = upper_price
        self.logger().info(
            f"Opening entry position: [{lower_price:.6f}, {upper_price:.6f}] at {price:.6f} (order {order_id})"
        )

    async def _open_breakeven(self, entry_lower: Decimal, breakeven_price: Decimal):
        if self.position_opening or self.position_opened:
            return
        base_amount, quote_amount = self._wallet_amounts(
            self.config.breakeven_base_pct, self.config.breakeven_quote_pct
        )
        if base_amount <= 0 and quote_amount <= 0:
            self.logger().warning("No available balance for breakeven.")
            return
        self.position_opening = True
        order_id = self.connectors[self.exchange].add_liquidity(
            trading_pair=self.config.trading_pair,
            price=float(breakeven_price),
            lower_price=float(entry_lower),
            upper_price=float(breakeven_price),
            base_token_amount=float(base_amount) if base_amount > 0 else None,
            quote_token_amount=float(quote_amount) if quote_amount > 0 else None,
            slippage_pct=float(self.config.slippage_pct) if self.config.slippage_pct is not None else None,
        )
        self.open_order_id = order_id
        self.state.phase = "breakeven"
        self.state.breakeven_price = breakeven_price
        self.logger().info(
            f"Opening breakeven position: [{entry_lower:.6f}, {breakeven_price:.6f}] (order {order_id})"
        )

    async def _close_position(self, reason: str, next_phase: str):
        if not self.position_info:
            return
        if self.position_closing:
            return
        self.position_closing = True
        order_id = self.connectors[self.exchange].remove_liquidity(
            trading_pair=self.config.trading_pair,
            position_address=self.position_info.address,
        )
        self.close_order_id = order_id
        self.pending_close_reason = reason
        self.pending_phase_after_close = next_phase
        self.logger().info(f"Closing position ({reason}) order {order_id}")

    def did_fill_order(self, event):
        if hasattr(event, "order_id") and event.order_id == self.open_order_id:
            self.logger().info(f"Open order {event.order_id} filled.")
            self.position_opened = True
            self.position_opening = False
            safe_ensure_future(self._fetch_position_after_open())
            return

        if hasattr(event, "order_id") and event.order_id == self.close_order_id:
            self.logger().info(f"Close order {event.order_id} filled.")
            self.position_opened = False
            self.position_closing = False
            self.position_info = None
            if self.pending_close_reason == "lower":
                self._compute_breakeven_after_close()
            else:
                self.state = StrategyState(phase=self.pending_phase_after_close or "idle")
            self.pending_close_reason = None
            self.pending_phase_after_close = None
            return

    async def _fetch_position_after_open(self):
        await asyncio.sleep(2)
        try:
            pool_address = await self._get_pool_address()
            if not pool_address:
                return
            positions = await self.connectors[self.exchange].get_user_positions(pool_address=pool_address)
            if positions:
                self.position_info = positions[-1]
                self.state.entry_lower_price = Decimal(str(self.position_info.lower_price))
                self.state.entry_upper_price = Decimal(str(self.position_info.upper_price))
        except Exception as e:
            self.logger().error(f"Error fetching position after open: {e}")

    def _compute_breakeven_after_close(self):
        entry_lower = self.state.entry_lower_price
        if entry_lower is None:
            self.logger().warning("Missing entry lower; resetting to idle.")
            self.state = StrategyState()
            return

        base_balance = self._get_balance(self.base_token)
        if base_balance <= 0:
            self.logger().warning("No base balance for breakeven; resetting to idle.")
            self.state = StrategyState()
            return

        target = Decimal(self.config.breakeven_target_quote)
        breakeven_price = (target / base_balance) ** 2 / entry_lower
        min_bps = Decimal(self.config.breakeven_min_bps_above_entry_lower) / Decimal(10_000)
        min_price = entry_lower * (Decimal("1") + min_bps)
        if breakeven_price <= entry_lower:
            breakeven_price = min_price

        self.state.phase = "await_breakeven_open"
        self.state.breakeven_price = breakeven_price
        self.logger().info(
            f"Computed breakeven price {breakeven_price:.6f} using base balance {base_balance:.6f}"
        )

    def _wallet_amounts(self, base_pct: Decimal, quote_pct: Decimal) -> tuple[Decimal, Decimal]:
        base_balance = self._get_balance(self.base_token)
        quote_balance = self._get_balance(self.quote_token)
        base_amount = base_balance * (base_pct / Decimal("100"))
        quote_amount = quote_balance * (quote_pct / Decimal("100"))
        return base_amount, quote_amount

    def _get_balance(self, token: str) -> Decimal:
        balance = self.connectors[self.exchange].get_balance(token)
        return Decimal(str(balance))

    def _price_in_entry_range(self, price: Decimal) -> bool:
        return self.config.entry_price_min <= price <= self.config.entry_price_max

    def _build_entry_bounds(self, price: Decimal) -> tuple[Decimal, Decimal]:
        width = Decimal(self.config.entry_width_bps) / Decimal(10_000)
        if width >= 1:
            raise ValueError("entry_width_bps must be < 10000")
        lower = price / (Decimal("1") + width)
        upper = price / (Decimal("1") - width)
        return lower, upper

    def _entry_bounds_from_state(self, price: Decimal) -> tuple[Decimal, Decimal]:
        if self.state.entry_lower_price is not None and self.state.entry_upper_price is not None:
            return self.state.entry_lower_price, self.state.entry_upper_price
        return self._build_entry_bounds(price)

    def _entry_lower_buffer(self) -> Decimal:
        return Decimal(self.config.entry_lower_buffer_bps) / Decimal(10_000)

    def format_status(self) -> str:
        lines = []
        lines.append(f"Phase: {self.state.phase}")
        if self.state.entry_lower_price and self.state.entry_upper_price:
            lines.append(f"Entry Range: {self.state.entry_lower_price:.6f} - {self.state.entry_upper_price:.6f}")
        if self.state.breakeven_price:
            lines.append(f"Breakeven Price: {self.state.breakeven_price:.6f}")
        if self.position_opening:
            lines.append(f"Opening order: {self.open_order_id}")
        if self.position_closing:
            lines.append(f"Closing order: {self.close_order_id}")
        if self.last_price is not None:
            lines.append(f"Last Price: {self.last_price:.6f}")
        if self.last_price_update:
            seconds_ago = (datetime.now() - self.last_price_update).total_seconds()
            lines.append(f"Last Update: {int(seconds_ago)}s ago")
        return "\n".join(lines)
