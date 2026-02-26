"""
Base Network Auto-Rebalance LP Strategy
========================================
Automatically rebalances LP position when price goes out of range.
Based on lp_manage_position.py with auto-rebalance feature.
"""
import asyncio
import logging
import os
import time
from decimal import Decimal
from typing import Dict, Optional, Union

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.common_types import ConnectorType, get_connector_type
from hummingbot.connector.gateway.gateway_lp import CLMMPoolInfo, CLMMPositionInfo
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class BaseAutoRebalanceLPConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    
    network: str = Field(
        "base",
        json_schema_extra={"prompt": "Network (base for Base mainnet)", "prompt_on_new": False}
    )
    
    trading_pair: str = Field(
        "WETH-USDC",
        json_schema_extra={"prompt": "Trading pair (WETH-USDC)", "prompt_on_new": True}
    )
    
    range_width_pct: Decimal = Field(
        Decimal("5.0"),
        json_schema_extra={"prompt": "Range width % (+/- from current price, e.g. 5 = ±5%)", "prompt_on_new": True}
    )
    
    base_token_amount: Decimal = Field(
        Decimal("0.01"),
        json_schema_extra={"prompt": "ETH amount per position", "prompt_on_new": True}
    )
    
    quote_token_amount: Decimal = Field(
        Decimal("25"),
        json_schema_extra={"prompt": "USDC amount per position", "prompt_on_new": True}
    )
    
    rebalance_delay: int = Field(
        300,
        json_schema_extra={"prompt": "Seconds out-of-range before rebalance (e.g. 300 = 5min)", "prompt_on_new": True}
    )
    
    check_interval: int = Field(
        30,
        json_schema_extra={"prompt": "Check interval in seconds", "prompt_on_new": False}
    )


class BaseAutoRebalanceLP(ScriptStrategyBase):
    """
    Auto-Rebalancing LP Strategy for Base Network
    
    - Opens LP position with symmetric range around current price
    - Monitors position continuously
    - When price goes out of range → waits → closes and reopens at new price
    """
    
    @classmethod
    def init_markets(cls, config: BaseAutoRebalanceLPConfig):
        connector_name = f"uniswap/clmm/{config.network}"
        cls.markets = {connector_name: {config.trading_pair}}
    
    def __init__(self, connectors: Dict[str, ConnectorBase], config: BaseAutoRebalanceLPConfig):
        super().__init__(connectors)
        self.config = config
        self.exchange = f"uniswap/clmm/{config.network}"
        self.base_token, self.quote_token = config.trading_pair.split("-")
        
        # State
        self.pool_info: Optional[CLMMPoolInfo] = None
        self.position_info: Optional[CLMMPositionInfo] = None
        self.position_opened = False
        self.position_opening = False
        self.position_closing = False
        
        # Tracking
        self.out_of_range_start_time: Optional[float] = None
        self.rebalance_count = 0
        self.open_order_id: Optional[str] = None
        self.close_order_id: Optional[str] = None
        self.last_check_time: Optional[float] = None
        
        self.log_with_clock(logging.INFO, "🚀 Base Auto-Rebalance LP Strategy Started")
        self.log_with_clock(logging.INFO, f"💰 Amount: {config.base_token_amount} ETH +{config.quote_token_amount} USDC")
        self.log_with_clock(logging.INFO, f"📊 Range: ±{config.range_width_pct}%")
        
        safe_ensure_future(self._startup())
    
    async def _startup(self):
        """Initialize and open first position"""
        await asyncio.sleep(3)
        await self.fetch_pool_info()
        
        if self.pool_info:
            self.log_with_clock(logging.INFO, f"✅ Pool found! Current price: ${self.pool_info.price:.2f}")
            await self.open_new_position()
        else:
            self.log_with_clock(logging.ERROR, "❌ Failed to fetch pool info")
    
    async def fetch_pool_info(self):
        """Get current pool information"""
        try:
            self.pool_info = await self.connectors[self.exchange].get_pool_info(
                trading_pair=self.config.trading_pair
            )
        except Exception as e:
            self.logger().error(f"Error fetching pool info: {e}")
    
    async def open_new_position(self):
        """Open a new LP position around current price"""
        if self.position_opening or self.position_opened:
            return
        
        self.position_opening = True
        
        try:
            await self.fetch_pool_info()
            if not self.pool_info:
                self.logger().error("Cannot open position: no pool info")
                self.position_opening = False
                return
            
            current_price = Decimal(str(self.pool_info.price))
            width_pct = self.config.range_width_pct / 100
            
            lower_price = current_price * (1 - width_pct)
            upper_price = current_price * (1 + width_pct)
            
            self.log_with_clock(logging.INFO, f"Opening position: ${lower_price:.2f} - ${upper_price:.2f}")
            
            order_id = self.connectors[self.exchange].add_liquidity(
                trading_pair=self.config.trading_pair,
                lower_price=float(lower_price),
                upper_price=float(upper_price),
                amount_0=float(self.config.base_token_amount),
                amount_1=float(self.config.quote_token_amount)
            )
            
            self.open_order_id = order_id
            self.log_with_clock(logging.INFO, f"✅ Position opening order submitted: {order_id}")
            
        except Exception as e:
            self.logger().error(f"Error opening position: {e}")
            self.position_opening = False
    
    async def monitor_position(self):
        """Check if position needs rebalancing"""
        if not self.position_opened or not self.position_info:
            return
        
        try:
            await self.fetch_pool_info()
            if not self.pool_info:
                return
            
            current_price = Decimal(str(self.pool_info.price))
            lower_price = Decimal(str(self.position_info.lower_price))
            upper_price = Decimal(str(self.position_info.upper_price))
            
            # Check if out of range
            out_of_range = current_price < lower_price or current_price > upper_price
            
            current_time = time.time()
            
            if out_of_range:
                if self.out_of_range_start_time is None:
                    self.out_of_range_start_time = current_time
                    self.log_with_clock(logging.INFO, f"⚠️ Price out of range: ${current_price:.2f} (range: ${lower_price:.2f}-${upper_price:.2f})")
                
                elapsed = current_time - self.out_of_range_start_time
                if elapsed >= self.config.rebalance_delay:
                    self.log_with_clock(logging.INFO, f"🔄 Rebalancing after {elapsed:.0f}s...")
                    await self.close_position_for_rebalance()
                else:
                    self.log_with_clock(logging.INFO, f"⏳ Out of range {elapsed:.0f}/{self.config.rebalance_delay}s")
            else:
                if self.out_of_range_start_time is not None:
                    self.log_with_clock(logging.INFO, f"✅ Back in range: ${current_price:.2f}")
                    self.out_of_range_start_time = None
        
        except Exception as e:
            self.logger().error(f"Error monitoring: {e}")
    
    async def close_position_for_rebalance(self):
        """Close position to prepare for rebalance"""
        if self.position_closing or not self.position_info:
            return
        
        self.position_closing = True
        
        try:
            self.log_with_clock(logging.INFO, f"Closing position {self.position_info.address}")
            
            order_id = self.connectors[self.exchange].remove_liquidity(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address
            )
            
            self.close_order_id = order_id
            self.log_with_clock(logging.INFO, f"✅ Position closing order submitted: {order_id}")
            
        except Exception as e:
            self.logger().error(f"Error closing position: {e}")
            self.position_closing = False
    
    def on_tick(self):
        """Main loop - runs every second"""
        current_time = time.time()
        
        # Check at specified interval
        if self.last_check_time is None or (current_time - self.last_check_time) >= self.config.check_interval:
            self.last_check_time = current_time
            
            if self.position_opened and not self.position_closing:
                safe_ensure_future(self.monitor_position())
    
    def did_fill_order(self, event):
        """Handle order fill events"""
        if hasattr(event, 'order_id'):
            # Position opened
            if event.order_id == self.open_order_id:
                self.log_with_clock(logging.INFO, f"✅ Position opened! (rebalance #{self.rebalance_count})")
                self.position_opened = True
                self.position_opening = False
                self.rebalance_count += 1
                
                safe_ensure_future(self._fetch_position_after_open())
                self.notify_hb_app_with_timestamp(f"LP position opened on Base (#{self.rebalance_count})")
            
            # Position closed (prepare for rebalance)
            elif event.order_id == self.close_order_id:
                self.log_with_clock(logging.INFO, "✅ Position closed, opening new position...")
                self.position_opened = False
                self.position_closing = False
                self.position_info = None
                self.out_of_range_start_time = None
                
                # Immediately open new position at current price
                safe_ensure_future(self.open_new_position())
                self.notify_hb_app_with_timestamp("LP position rebalanced on Base")
    
    async def _fetch_position_after_open(self):
        """Fetch position info after opening"""
        try:
            await asyncio.sleep(2)
            positions = await self.connectors[self.exchange].get_user_positions()
            if positions:
                self.position_info = positions[-1]
                self.log_with_clock(logging.INFO, f"Position info fetched: {self.position_info.address}")
        except Exception as e:
            self.logger().error(f"Error fetching position: {e}")
    
    def format_status(self) -> str:
        """Display status"""
        lines = ["\n" + "="*60]
        lines.append(f"🎯 Base Auto-Rebalance LP | {self.config.trading_pair}")
        lines.append("="*60)
        
        if self.pool_info:
            lines.append(f"Current Price: ${Decimal(str(self.pool_info.price)):,.2f}")
        
        lines.append(f"Rebalances: {self.rebalance_count}")
        
        if self.position_closing:
            lines.append("\n⏳ Status: Closing position...")
        elif self.position_opening:
            lines.append("\n⏳ Status: Opening position...")
        elif self.position_opened and self.position_info:
            lower = Decimal(str(self.position_info.lower_price))
            upper = Decimal(str(self.position_info.upper_price))
            
            lines.append(f"\n✅ Position: ${lower:,.2f} - ${upper:,.2f}")
            
            base_amt = Decimal(str(self.position_info.base_token_amount))
            quote_amt = Decimal(str(self.position_info.quote_token_amount))
            lines.append(f"Tokens: {base_amt:.4f} {self.base_token} / {quote_amt:.2f} {self.quote_token}")
            
            if self.out_of_range_start_time:
                elapsed = time.time() - self.out_of_range_start_time
                lines.append(f"⚠️ Out of range: {elapsed:.0f}/{self.config.rebalance_delay}s")
        else:
            lines.append("\n⏳ Status: Initializing...")
        
        lines.append("="*60)
        return "\n".join(lines)
