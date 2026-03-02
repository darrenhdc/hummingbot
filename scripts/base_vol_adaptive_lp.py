"""
Base Mainnet ETH/USDC 波动率自适应 LP 策略
改编自 strategy_000_vol_adaptive
"""

import json
import logging
import math
import os
import time
from decimal import Decimal
from typing import Dict, Optional

from pydantic import Field, field_validator

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

    # 风险参数（统一配置校验）
    max_position_pct: Decimal = Field(
        Decimal("50"),
        json_schema_extra={"prompt": "仓位上限占总资产百分比（<=50）", "prompt_on_new": True}
    )

    gas_token: str = Field(
        "ETH",
        json_schema_extra={"prompt": "Gas token symbol", "prompt_on_new": True}
    )

    min_gas_reserve: Decimal = Field(
        Decimal("0.02"),
        json_schema_extra={"prompt": "最小 gas 预留", "prompt_on_new": True}
    )

    stop_loss_pct: Decimal = Field(
        Decimal("10"),
        json_schema_extra={"prompt": "止损百分比（正数）", "prompt_on_new": True}
    )

    strategy_id: str = Field(
        "base_vol_adaptive_lp",
        json_schema_extra={"prompt": "Strategy ID for analytics adapter", "prompt_on_new": False}
    )

    analytics_output_path: str = Field(
        "logs/base_vol_adaptive_lp_events.jsonl",
        json_schema_extra={"prompt": "Analytics adapter output jsonl path", "prompt_on_new": False}
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

    @field_validator("max_position_pct")
    @classmethod
    def validate_max_position_pct(cls, v: Decimal):
        if v <= 0 or v > 50:
            raise ValueError("max_position_pct must be in (0, 50]")
        return v

    @field_validator("min_gas_reserve")
    @classmethod
    def validate_min_gas_reserve(cls, v: Decimal):
        if v <= 0:
            raise ValueError("min_gas_reserve must be > 0")
        return v

    @field_validator("stop_loss_pct")
    @classmethod
    def validate_stop_loss_pct(cls, v: Decimal):
        if v <= 0 or v >= 100:
            raise ValueError("stop_loss_pct must be in (0, 100)")
        return v


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
        # 连接器名称为 2 段格式，网络由 Gateway defaultNetwork 自动决定
        connector_name = "uniswap/clmm"
        cls.markets = {connector_name: {config.trading_pair}}
    
    def __init__(self, connectors: Dict[str, ConnectorBase], config: BaseVolAdaptiveLPConfig):
        super().__init__(connectors)
        self.config = config
        self.exchange = "uniswap/clmm"
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
        self.last_adapter_event: Optional[Dict] = None
        
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
            sigma_ratio = None
            from scripts.market_indicators import get_realized_vol_7d

            sigma_percent = get_realized_vol_7d()
            if sigma_percent is not None:
                sigma_ratio = float(sigma_percent) / 100.0
            
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
            self.log_with_clock(logging.WARNING, f"⚠️  波动率源异常，使用 fallback: {e}")
            return self.fallback_width_bps
    
    async def _open_position(self):
        """开仓"""
        if self.position_opening or self.position_opened:
            return
        
        try:
            self.position_opening = True
            current_price = Decimal(str(self.pool_info.price))

            if not self._has_sufficient_gas_reserve():
                self.log_with_clock(logging.WARNING, "⛔ gas reserve 不足，拒绝开仓")
                self._emit_adapter_event(
                    action="hold",
                    reason="gas_reserve_insufficient",
                    price=current_price,
                    gas_cost=None,
                )
                return

            if not self._within_max_position_exposure(current_price):
                self.log_with_clock(logging.WARNING, "⛔ 超过 max_position_pct 总暴露上限，拒绝开仓")
                self._emit_adapter_event(
                    action="hold",
                    reason="max_position_pct_exceeded",
                    price=current_price,
                    gas_cost=None,
                )
                return
            
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
            self._emit_adapter_event(
                action="open",
                reason="entry_opened",
                price=current_price,
                range_lower=lower_price,
                range_upper=upper_price,
                in_range=True,
                gas_cost=None,
            )
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 开仓失败: {e}")
        finally:
            self.position_opening = False
    
    async def _rebalance_position(self, current_price: Decimal):
        """重新平衡仓位"""
        if self.position_rebalancing or not self.position_info:
            return
        
        try:
            self.position_rebalancing = True
            self.rebalance_count += 1
            
            self.log_with_clock(logging.INFO, f"🔄 开始重新平衡 (第 {self.rebalance_count} 次)...")

            self._emit_adapter_event(
                action="rebalance",
                reason="out_of_range",
                price=current_price,
                range_lower=Decimal(str(self.position_info.lower_price)),
                range_upper=Decimal(str(self.position_info.upper_price)),
                in_range=False,
                gas_cost=None,
            )
            
            # 1. 关闭当前仓位
            order_id = await self.connectors[self.exchange].close_position(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address,
            )
            
            self.log_with_clock(logging.INFO, f"✅ 旧仓位已关闭: {order_id}")
            self._emit_adapter_event(
                action="close",
                reason="rebalance_close",
                price=current_price,
                range_lower=Decimal(str(self.position_info.lower_price)),
                range_upper=Decimal(str(self.position_info.upper_price)),
                in_range=False,
                gas_cost=None,
            )
            
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

            # 强制止损路径
            if self.entry_price and self.entry_price > 0:
                drawdown_pct = (self.entry_price - current_price) / self.entry_price * Decimal(100)
                if drawdown_pct >= self.config.stop_loss_pct:
                    self.log_with_clock(
                        logging.WARNING,
                        f"🛑 Stop-loss 触发: drawdown={drawdown_pct:.2f}% >= {self.config.stop_loss_pct}%",
                    )
                    await self._close_position(reason="stop_loss", current_price=current_price)
                    return

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
                await self._rebalance_position(current_price=current_price)
            
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 监控仓位失败: {e}")

    async def _close_position(self, reason: str, current_price: Decimal):
        """执行平仓并输出最小 analytics adapter 事件"""
        if not self.position_info or self.position_closing:
            return

        try:
            self.position_closing = True
            order_id = await self.connectors[self.exchange].close_position(
                trading_pair=self.config.trading_pair,
                position_address=self.position_info.address,
            )
            self.log_with_clock(logging.INFO, f"✅ 平仓成功: {order_id}, reason={reason}")

            self._emit_adapter_event(
                action="close",
                reason=reason,
                price=current_price,
                range_lower=Decimal(str(self.position_info.lower_price)),
                range_upper=Decimal(str(self.position_info.upper_price)),
                in_range=bool(self.position_info.in_range),
                gas_cost=None,
            )

            self.position_opened = False
            self.position_info = None
        except Exception as e:
            self.log_with_clock(logging.ERROR, f"❌ 平仓失败: {e}")
        finally:
            self.position_closing = False

    def _has_sufficient_gas_reserve(self) -> bool:
        gas_balance = Decimal(str(self.connectors[self.exchange].get_balance(self.config.gas_token)))
        return gas_balance >= self.config.min_gas_reserve

    def _within_max_position_exposure(self, current_price: Decimal) -> bool:
        """总暴露口径：拟开仓价值 <= (钱包总价值 * max_position_pct)。"""
        base_balance = Decimal(str(self.connectors[self.exchange].get_balance(self.base_token)))
        quote_balance = Decimal(str(self.connectors[self.exchange].get_balance(self.quote_token)))
        wallet_total_quote = quote_balance + base_balance * current_price
        max_allowed_quote = wallet_total_quote * (self.config.max_position_pct / Decimal(100))
        intended_exposure_quote = self.config.entry_amount_usdc + self.config.entry_amount_eth * current_price
        return intended_exposure_quote <= max_allowed_quote

    def _estimate_fees_collected(self, current_price: Decimal) -> Optional[Decimal]:
        if not self.position_info:
            return None
        base_fee = Decimal(str(getattr(self.position_info, "base_fee_amount", 0)))
        quote_fee = Decimal(str(getattr(self.position_info, "quote_fee_amount", 0)))
        return base_fee * current_price + quote_fee

    def _estimate_il_pct(self, current_price: Decimal) -> Optional[Decimal]:
        if not self.entry_price or self.entry_price <= 0:
            return None
        ratio = float(current_price / self.entry_price)
        if ratio <= 0:
            return None
        il = (2 * math.sqrt(ratio) / (1 + ratio) - 1) * 100
        return Decimal(str(il))

    def _build_adapter_event(
        self,
        *,
        action: str,
        reason: str,
        price: Decimal,
        range_lower: Optional[Decimal] = None,
        range_upper: Optional[Decimal] = None,
        in_range: Optional[bool] = None,
        gas_cost: Optional[Decimal] = None,
    ) -> Dict:
        fees_collected = self._estimate_fees_collected(price)
        estimated_il_pct = self._estimate_il_pct(price)
        return {
            "strategy_id": self.config.strategy_id,
            "timestamp": int(time.time()),
            "action": action,
            "reason": reason,
            "price": float(price),
            "range_lower": float(range_lower) if range_lower is not None else None,
            "range_upper": float(range_upper) if range_upper is not None else None,
            "in_range": in_range,
            "fees_collected": float(fees_collected) if fees_collected is not None else None,
            "estimated_il_pct": float(estimated_il_pct) if estimated_il_pct is not None else None,
            "gas_cost": float(gas_cost) if gas_cost is not None else None,
        }

    def _emit_adapter_event(self, **kwargs):
        event = self._build_adapter_event(**kwargs)
        self.last_adapter_event = event
        self.log_with_clock(logging.INFO, f"[adapter] {json.dumps(event, ensure_ascii=False)}")

        raw_output_path = (self.config.analytics_output_path or "").strip()
        if raw_output_path == "":
            self.log_with_clock(logging.WARNING, "⚠️ analytics_output_path 为空，跳过 adapter 文件输出")
            return

        output_path = raw_output_path
        if not os.path.isabs(output_path):
            output_path = os.path.join(os.getcwd(), output_path)

        # 边界修复：当配置为纯文件名（无目录）时，不应对空 dirname 调用 makedirs。
        raw_dirname = os.path.dirname(raw_output_path)
        if raw_dirname:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            self.log_with_clock(logging.WARNING, f"⚠️ adapter 输出失败: {e}")
    
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
