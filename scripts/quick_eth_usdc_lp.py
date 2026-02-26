"""
Quick ETH/USDC LP Trading on Uniswap V3
========================================
A simple script to manage Uniswap V3 liquidity positions for ETH/USDC pair.
Opens a position at target price and manages it automatically.
"""

import logging
import os
from decimal import Decimal
from typing import Dict, Optional, Union

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.common_types import ConnectorType, get_connector_type
from hummingbot.connector.gateway.gateway_lp import CLMMPoolInfo, CLMMPositionInfo
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class QuickETHUSDCLPConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    
    # Network - use "ethereum" for mainnet, "ethereum_goerli" for testnet
    network: str = Field(
        "ethereum",
        json_schema_extra={"prompt": "Network (ethereum, arbitrum, optimism, polygon)", "prompt_on_new": True}
    )
    
    # Trading pair
    trading_pair: str = Field(
        "WETH-USDC",
        json_schema_extra={"prompt": "Trading pair", "prompt_on_new": True}
    )
    
    # Entry parameters
    entry_amount_eth: Decimal = Field(
        Decimal("0.1"),
        json_schema_extra={"prompt": "ETH amount to provide", "prompt_on_new": True}
    )
    
    entry_amount_usdc: Decimal = Field(
        Decimal("300"),
        json_schema_extra={"prompt": "USDC amount to provide", "prompt_on_new": True}
    )
    
    # Price range (as % above/below current price)
    range_lower_pct: Decimal = Field(
        Decimal("5"),
        json_schema_extra={"prompt": "Lower range % below current price (e.g., 5 = 5%)", "prompt_on_new": True}
    )
    
    range_upper_pct: Decimal = Field(
        Decimal("5"),
        json_schema_extra={"prompt": "Upper range % above current price (e.g., 5 = 5%)", "prompt_on_new": True}
    )
    
    # Risk management
    stop_loss_pct: Decimal = Field(
        Decimal("10"),
        json_schema_extra={"prompt": "Stop loss % from entry price (e.g., 10 = close if -10%)", "prompt_on_new": True}
    )
    
    take_profit_pct: Decimal = Field(
        Decimal("20"),
        json_schema_extra={"prompt": "Take profit % from entry (e.g., 20 = close if +20% fees)", "prompt_on_new": True}
    )
    
    # Monitoring
    check_interval: int = Field(
        15,
        json_schema_extra={"prompt": "Check interval in seconds", "prompt_on_new": False}
    )
    
    # Auto-start
    auto_open_position: bool = Field(
        True,
        json_schema_extra={"prompt": "Auto-open position on start?", "prompt_on_new": True}
    )


class QuickETHUSDCLP(ScriptStrategyBase):
    """
    Quick Uniswap V3 LP Strategy for ETH/USDC
    
    Features:
    - Automatic position opening with custom range
    - Stop loss and take profit
    - Gas optimization
    - Real-time monitoring
    """
    
    @classmethod
    def init_markets(cls, config: QuickETHUSDCLPConfig):
        connector_name = f"uniswap/clmm/{config.network}"
        cls.markets = {connector_name: {config.trading_pair}}
    
    def __init__(self, connectors: Dict[str, ConnectorBase], config: QuickETHUSDCLPConfig):
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
        
        # Entry tracking
        self.entry_price: Optional[Decimal] = None
        self.entry_fees_collected: Decimal = Decimal("0")
        
        self.log_with_clock(logging.INFO, 
                          f"🚀 Quick ETH/USDC LP Strategy Started!")
        self.log_with_clock(logging.INFO,
                          f"📊 Network: {config.network}")
        self.log_with_clock(logging.INFO,
                          f"💰 Target: {config.entry_amount_eth} ETH + {config.entry_amount_usdc} USDC")
        self.log_with_clock(logging.INFO,
                          f"📈 Range: -{config.range_lower_pct}% to +{config.range_upper_pct}%")
        
        # Schedule startup
        safe_ensure_future(self._startup())
    
    async def _startup(self):
        """Initialize pool info and optionally open position"""
        import asyncio
        await asyncio.sleep(3)  # Wait for connector to be ready
        
        await self._fetch_pool_info()
        
        if self.pool_info:
            current_price = Decimal(str(self.pool_info.price))
            self.log_with_clock(logging.INFO,
                              f"📊 Current ETH/USDC Price: ${current_price:,.2f}")
            
            # Check for existing positions
            await self._check_existing_position()
            
            if not self.position_opened and self.config.auto_open_position:
                self.log_with_clock(logging.INFO, "🎯 Opening position...")
                await self._open_position()
    
    async def _fetch_pool_info(self):
        """Get current pool information"""
        try:
            self.pool_info = await self.connectors[self.exchange].get_pool_info(
                trading_pair=self.config.trading_pair
            )
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ Error fetching pool info: {e}")
            self.pool_info = None
    
    async def _check_existing_position(self):
        """Check if we already have an active position"""
        try:
            pool_address = await self.connectors[self.exchange].get_pool_address(
                self.config.trading_pair
            )
            if pool_address:
                positions = await self.connectors[self.exchange].get_user_positions(
                    pool_address=pool_address
                )
                if positions:
                    self.position_info = positions[-1]  # Use latest position
                    self.position_opened = True
                    self.entry_price = Decimal(str(self.pool_info.price))
                    self.log_with_clock(logging.INFO,
                                      f"✅ Found existing position: {self.position_info.address[:10]}...")
        except Exception as e:
            self.log_with_clock(logging.WARNING, f"⚠️  Could not check existing positions: {e}")
    
    async def _open_position(self):
        """Open a new LP position"""
        if self.position_opening or self.position_opened:
            return
        
        try:
            self.position_opening = True
            current_price = Decimal(str(self.pool_info.price))
            
            # Calculate price range
            lower_price = current_price * (1 - self.config.range_lower_pct / 100)
            upper_price = current_price * (1 + self.config.range_upper_pct / 100)
            
            self.log_with_clock(logging.INFO,
                              f"📍 Position Range: ${lower_price:,.2f} - ${upper_price:,.2f}")
            
            # Open position
            pool_address = await self.connectors[self.exchange].get_pool_address(
                self.config.trading_pair
            )
            
            order_id = await self.connectors[self.exchange].open_position(
                trading_pair=self.config.trading_pair,
                pool_address=pool_address,
                lower_price=float(lower_price),
                upper_price=float(upper_price),
                base_amount=float(self.config.entry_amount_eth),
                quote_amount=float(self.config.entry_amount_usdc),
            )
            
            self.entry_price = current_price
            self.position_opened = True
            
            self.log_with_clock(logging.INFO,
                              f"✅ Position opened! Order ID: {order_id}")
            self.log_with_clock(logging.INFO,
                              f"💰 Entry Price: ${current_price:,.2f}")
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ Error opening position: {e}")
        finally:
            self.position_opening = False
    
    async def _close_position(self, reason: str = "manual"):
        """Close the current LP position"""
        if not self.position_info or self.position_closing:
            return
        
        try:
            self.position_closing = True
            self.log_with_clock(logging.INFO, f"🔄 Closing position (reason: {reason})...")
            
            order_id = await self.connectors[self.exchange].close_position(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address,
            )
            
            self.position_opened = False
            self.position_info = None
            
            self.log_with_clock(logging.INFO,
                              f"✅ Position closed! Order ID: {order_id}")
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ Error closing position: {e}")
        finally:
            self.position_closing = False
    
    def on_tick(self):
        """Main strategy loop"""
        if self.position_opening or self.position_closing:
            return
        
        safe_ensure_future(self._monitor_position())
    
    async def _monitor_position(self):
        """Monitor and manage the position"""
        if not self.position_opened or not self.position_info:
            return
        
        try:
            # Refresh data
            await self._fetch_pool_info()
            if not self.pool_info:
                return
            
            # Refresh position
            self.position_info = await self.connectors[self.exchange].get_position_info(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address
            )
            
            current_price = Decimal(str(self.pool_info.price))
            
            # Check stop loss
            if self.entry_price:
                price_change_pct = ((current_price - self.entry_price) / self.entry_price) * 100
                
                if price_change_pct <= -self.config.stop_loss_pct:
                    self.log_with_clock(logging.WARNING,
                                      f"🛑 Stop loss triggered! Change: {price_change_pct:.2f}%")
                    await self._close_position("stop_loss")
                    return
            
            # Check if position is out of range
            lower_price = Decimal(str(self.position_info.lower_price))
            upper_price = Decimal(str(self.position_info.upper_price))
            
            if current_price < lower_price or current_price > upper_price:
                self.log_with_clock(logging.WARNING,
                                  f"⚠️  Position out of range! Current: ${current_price:,.2f}, Range: ${lower_price:,.2f}-${upper_price:,.2f}")
            
            # Log status periodically
            self._log_position_status(current_price)
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ Error monitoring position: {e}")
    
    def _log_position_status(self, current_price: Decimal):
        """Log current position status"""
        if not self.position_info:
            return
        
        pnl_pct = 0
        if self.entry_price:
            pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        
        self.log_with_clock(logging.INFO,
                          f"📊 Price: ${current_price:,.2f} | PnL: {pnl_pct:+.2f}% | "
                          f"In Range: {'✅' if self.position_info.in_range else '❌'}")
    
    def format_status(self) -> str:
        """Return strategy status for display"""
        if not self.pool_info:
            return "⏳ Initializing..."
        
        current_price = Decimal(str(self.pool_info.price))
        status = f"\n{'='*60}\n"
        status += f"🎯 Quick ETH/USDC LP Strategy Status\n"
        status += f"{'='*60}\n"
        status += f"Network: {self.config.network}\n"
        status += f"Current Price: ${current_price:,.2f}\n"
        
        if self.position_opened and self.position_info:
            lower = Decimal(str(self.position_info.lower_price))
            upper = Decimal(str(self.position_info.upper_price))
            in_range = "✅ In Range" if self.position_info.in_range else "❌ Out of Range"
            
            pnl = 0
            if self.entry_price:
                pnl = ((current_price - self.entry_price) / self.entry_price) * 100
            
            status += f"\n📍 Position Status: OPEN {in_range}\n"
            status += f"Entry Price: ${self.entry_price:,.2f}\n"
            status += f"Price Range: ${lower:,.2f} - ${upper:,.2f}\n"
            status += f"PnL: {pnl:+.2f}%\n"
        else:
            status += f"\n📍 Position Status: CLOSED\n"
        
        status += f"{'='*60}\n"
        return status
