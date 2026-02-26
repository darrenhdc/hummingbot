"""
Base Mainnet ETH/USDC 波动率自适应 LP 策略
改编自 strategy_000_vol_adaptive
"""

import logging
import os
from decimal import Decimal
from typing import Dict, Optional

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.gateway.common_types import ConnectorType, get_connector_type
from hummingbot.connector.gateway.gateway_lp import CLMMPoolInfo, CLMMPositionInfo
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class BaseVolAdaptiveLPConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    
    # 网络配置
    network: str = Field(
        "base",
        json_schema_extra={"prompt": "Network (base)", "prompt_on_new": False}
    )
    
    # 交易对（Base 上的 WETH/USDC）
    trading_pair: str = Field(
        "WETH-USDC",
        json_schema_extra={"prompt": "Trading pair (Base mainnet WETH-USDC)", "prompt_on_new": True}
    )
    
    # 小额测试参数
    entry_amount_eth: Decimal = Field(
        Decimal("0.01"),  # 极小金额，约 $20-30
        json_schema_extra={"prompt": "ETH amount (建议 0.01 用于测试)", "prompt_on_new": True}
    )
    
    entry_amount_usdc: Decimal = Field(
        Decimal("25"),  # 极小金额
        json_schema_extra={"prompt": "USDC amount (建议 25 用于测试)", "prompt_on_new": True}
    )
    
    # 波动率自适应参数
    w_min: int = Field(
        150,
        json_schema_extra={"prompt": "最小区间宽度 bps (150 = 1.5%)", "prompt_on_new": False}
    )
    
    w_max: int = Field(
        400,
        json_schema_extra={"prompt": "最大区间宽度 bps (400 = 4%)", "prompt_on_new": False}
    )
    
    sigma_0: Decimal = Field(
        Decimal("0.80"),
        json_schema_extra={"prompt": "基准波动率 (0.80 = 80%)", "prompt_on_new": False}
    )
    
    k: Decimal = Field(
        Decimal("200"),
        json_schema_extra={"prompt": "敏感度系数", "prompt_on_new": False}
    )
    
    fallback_width_bps: int = Field(
        200,
        json_schema_extra={"prompt": "备用区间宽度 bps (200 = 2%)", "prompt_on_new": False}
    )
    
    # 监控间隔
    check_interval: int = Field(
        30,
        json_schema_extra={"prompt": "检查间隔（秒）", "prompt_on_new": False}
    )
    
    # 自动开仓
    auto_open_position: bool = Field(
        True,
        json_schema_extra={"prompt": "启动时自动开仓?", "prompt_on_new": True}
    )


class BaseVolAdaptiveLP(ScriptStrategyBase):
    """
    Base Mainnet 波动率自适应 LP 策略
    
    特点：
    - 🔄 仓位在区间内：保持不动
    - 📊 仓位出区间：根据波动率重新平衡
    - 📈 波动率高 → 宽区间（更安全）
    - 📉 波动率低 → 窄区间（更多手续费）
    """
    
    @classmethod
    def init_markets(cls, config: BaseVolAdaptiveLPConfig):
        # Base mainnet 使用 uniswap/clmm
        connector_name = f"uniswap/clmm/{config.network}"
        cls.markets = {connector_name: {config.trading_pair}}
    
    def __init__(self, connectors: Dict[str, ConnectorBase], config: BaseVolAdaptiveLPConfig):
        super().__init__(connectors)
        self.config = config
        self.exchange = f"uniswap/clmm/{config.network}"
        self.base_token, self.quote_token = config.trading_pair.split("-")
        
        # 策略参数
        self.w_min = int(config.w_min)
        self.w_max = int(config.w_max)
        self.sigma_0 = float(config.sigma_0)
        self.k = float(config.k)
        self.fallback_width_bps = int(config.fallback_width_bps)
        
        # 状态
        self.pool_info: Optional[CLMMPoolInfo] = None
        self.position_info: Optional[CLMMPositionInfo] = None
        self.position_opened = False
        self.position_opening = False
        self.position_closing = False
        self.position_rebalancing = False
        
        # 追踪
        self.entry_price: Optional[Decimal] = None
        self.rebalance_count = 0
        
        self.log_with_clock(logging.INFO, "🚀 Base Mainnet 波动率自适应 LP 策略已启动")
        self.log_with_clock(logging.INFO, f"💰 测试金额: {config.entry_amount_eth} ETH + {config.entry_amount_usdc} USDC")
        self.log_with_clock(logging.INFO, f"📊 区间范围: {self.w_min/100:.2f}% - {self.w_max/100:.2f}%")
        
        safe_ensure_future(self._startup())
    
    async def _startup(self):
        """初始化"""
        import asyncio
        await asyncio.sleep(3)
        
        await self._fetch_pool_info()
        
        if self.pool_info:
            current_price = Decimal(str(self.pool_info.price))
            self.log_with_clock(logging.INFO, f"📊 Base ETH/USDC 当前价格: ${current_price:,.2f}")
            
            # 检查现有仓位
            await self._check_existing_position()
            
            if not self.position_opened and self.config.auto_open_position:
                self.log_with_clock(logging.INFO, "🎯 开始开仓...")
                await self._open_position()
    
    async def _fetch_pool_info(self):
        """获取池子信息"""
        try:
            self.pool_info = await self.connectors[self.exchange].get_pool_info(
                trading_pair=self.config.trading_pair
            )
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 获取池子信息失败: {e}")
            self.pool_info = None
    
    async def _check_existing_position(self):
        """检查现有仓位"""
        try:
            pool_address = await self.connectors[self.exchange].get_pool_address(
                self.config.trading_pair
            )
            if pool_address:
                positions = await self.connectors[self.exchange].get_user_positions(
                    pool_address=pool_address
                )
                if positions:
                    self.position_info = positions[-1]
                    self.position_opened = True
                    self.entry_price = Decimal(str(self.pool_info.price))
                    self.log_with_clock(logging.INFO, 
                                      f"✅ 发现现有仓位: {self.position_info.address[:10]}...")
                    self._log_position_details()
        except Exception as e:
            self.log_with_clock(logging.WARNING, f"⚠️  检查现有仓位失败: {e}")
    
    def _calculate_range_width(self) -> int:
        """计算动态区间宽度（基于波动率）"""
        try:
            # TODO: 接入真实波动率数据源
            # 现在使用简化版本：根据最近价格变动估算
            sigma_ratio = None
            
            # 这里可以接入您的波动率指标
            # from market_indicators import get_realized_vol_7d
            # sigma_percent = get_realized_vol_7d()
            # if sigma_percent:
            #     sigma_ratio = float(sigma_percent) / 100.0
            
            if sigma_ratio is not None:
                # 波动率公式：区间 = w_min + k × (σ - σ0)
                width_raw = self.w_min + self.k * (sigma_ratio - self.sigma_0)
                width_bps = int(round(min(max(width_raw, self.w_min), self.w_max)))
                self.log_with_clock(logging.INFO, 
                                  f"📈 根据波动率计算区间: {width_bps/100:.2f}% (σ={sigma_ratio:.2%})")
                return width_bps
            else:
                self.log_with_clock(logging.INFO, 
                                  f"📊 使用备用区间宽度: {self.fallback_width_bps/100:.2f}%")
                return self.fallback_width_bps
        except Exception as e:
            self.log_with_clock(logging.WARNING, f"⚠️  计算区间宽度失败: {e}")
            return self.fallback_width_bps
    
    async def _open_position(self):
        """开仓"""
        if self.position_opening or self.position_opened:
            return
        
        try:
            self.position_opening = True
            current_price = Decimal(str(self.pool_info.price))
            
            # 计算动态区间
            width_bps = self._calculate_range_width()
            width_pct = Decimal(width_bps) / Decimal(10000)
            
            lower_price = current_price * (1 - width_pct)
            upper_price = current_price * (1 + width_pct)
            
            self.log_with_clock(logging.INFO,
                              f"📍 开仓区间: ${lower_price:,.2f} - ${upper_price:,.2f}")
            self.log_with_clock(logging.INFO,
                              f"   区间宽度: {width_bps/100:.2f}% (±{width_bps/200:.2f}%)")
            
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
            
            self.log_with_clock(logging.INFO, f"✅ 开仓成功! Order ID: {order_id}")
            self.log_with_clock(logging.INFO, f"💰 开仓价格: ${current_price:,.2f}")
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 开仓失败: {e}")
        finally:
            self.position_opening = False
    
    async def _rebalance_position(self):
        """重新平衡仓位"""
        if self.position_rebalancing or not self.position_info:
            return
        
        try:
            self.position_rebalancing = True
            self.rebalance_count += 1
            
            self.log_with_clock(logging.INFO, f"🔄 开始重新平衡 (第 {self.rebalance_count} 次)...")
            
            # 1. 关闭当前仓位
            await self.connectors[self.exchange].close_position(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address,
            )
            
            self.log_with_clock(logging.INFO, "✅ 旧仓位已关闭")
            
            # 2. 等待确认
            import asyncio
            await asyncio.sleep(3)
            
            # 3. 计算新区间并开仓
            self.position_opened = False
            self.position_info = None
            
            await self._fetch_pool_info()
            await self._open_position()
            
            self.log_with_clock(logging.INFO, f"✅ 重新平衡完成!")
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 重新平衡失败: {e}")
        finally:
            self.position_rebalancing = False
    
    def on_tick(self):
        """主循环"""
        if self.position_opening or self.position_closing or self.position_rebalancing:
            return
        
        safe_ensure_future(self._monitor_position())
    
    async def _monitor_position(self):
        """监控仓位"""
        if not self.position_opened or not self.position_info:
            return
        
        try:
            await self._fetch_pool_info()
            if not self.pool_info:
                return
            
            # 刷新仓位信息
            self.position_info = await self.connectors[self.exchange].get_position_info(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address
            )
            
            current_price = Decimal(str(self.pool_info.price))
            lower_price = Decimal(str(self.position_info.lower_price))
            upper_price = Decimal(str(self.position_info.upper_price))
            
            # 核心策略逻辑：检查是否在区间内
            is_in_range = lower_price <= current_price <= upper_price
            
            if is_in_range:
                # 在区间内 → 保持不动
                self._log_position_status(current_price, "✅ 在区间内")
            else:
                # 出区间 → 触发重新平衡
                direction = "下方" if current_price < lower_price else "上方"
                self.log_with_clock(logging.WARNING,
                                  f"⚠️  价格已出区间! 当前: ${current_price:,.2f} 在区间{direction}")
                self.log_with_clock(logging.INFO, 
                                  f"   原区间: ${lower_price:,.2f} - ${upper_price:,.2f}")
                
                # 执行重新平衡
                await self._rebalance_position()
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 监控仓位失败: {e}")
    
    def _log_position_status(self, current_price: Decimal, status: str):
        """记录仓位状态"""
        if not self.position_info:
            return
        
        lower = Decimal(str(self.position_info.lower_price))
        upper = Decimal(str(self.position_info.upper_price))
        
        # 计算价格在区间中的位置
        range_size = upper - lower
        price_position = (current_price - lower) / range_size * 100 if range_size > 0 else 0
        
        self.log_with_clock(logging.INFO,
                          f"📊 {status} | 价格: ${current_price:,.2f} | "
                          f"区间位置: {price_position:.1f}% | "
                          f"重新平衡次数: {self.rebalance_count}")
    
    def _log_position_details(self):
        """记录仓位详情"""
        if not self.position_info:
            return
        
        lower = Decimal(str(self.position_info.lower_price))
        upper = Decimal(str(self.position_info.upper_price))
        width = (upper - lower) / lower * 100
        
        self.log_with_clock(logging.INFO, "=" * 60)
        self.log_with_clock(logging.INFO, "📍 仓位详情:")
        self.log_with_clock(logging.INFO, f"   地址: {self.position_info.address[:20]}...")
        self.log_with_clock(logging.INFO, f"   下限: ${lower:,.2f}")
        self.log_with_clock(logging.INFO, f"   上限: ${upper:,.2f}")
        self.log_with_clock(logging.INFO, f"   宽度: {width:.2f}%")
        self.log_with_clock(logging.INFO, f"   状态: {'✅ 在区间内' if self.position_info.in_range else '❌ 出区间'}")
        self.log_with_clock(logging.INFO, "=" * 60)
    
    def format_status(self) -> str:
        """格式化状态输出"""
        if not self.pool_info:
            return "⏳ 正在初始化..."
        
        current_price = Decimal(str(self.pool_info.price))
        status = f"\n{'='*60}\n"
        status += f"🎯 Base Mainnet 波动率自适应 LP 策略\n"
        status += f"{'='*60}\n"
        status += f"当前价格: ${current_price:,.2f}\n"
        status += f"重新平衡次数: {self.rebalance_count}\n"
        
        if self.position_opened and self.position_info:
            lower = Decimal(str(self.position_info.lower_price))
            upper = Decimal(str(self.position_info.upper_price))
            width = (upper - lower) / lower * 100
            in_range = "✅ 在区间内" if self.position_info.in_range else "❌ 出区间"
            
            status += f"\n📍 仓位状态: {in_range}\n"
            status += f"区间: ${lower:,.2f} - ${upper:,.2f}\n"
            status += f"宽度: {width:.2f}%\n"
        else:
            status += f"\n📍 仓位状态: 未开仓\n"
        
        status += f"{'='*60}\n"
        return status
