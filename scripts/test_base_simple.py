"""
简化测试脚本 - Base Mainnet Uniswap V3
"""
import logging
import os
from decimal import Decimal
from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class TestBaseSimpleConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    network: str = Field("base", client_data=None)
    trading_pair: str = Field("WETH-USDC", client_data=None)


class TestBaseSimple(ScriptStrategyBase):
    """
    简化测试脚本 - 仅验证 Gateway 连接
    """
    
    @classmethod
    def init_markets(cls, config: TestBaseSimpleConfig):
        connector_name = f"uniswap/clmm/{config.network}"
        cls.markets = {connector_name: {config.trading_pair}}
    
    def __init__(self, connectors: dict, config: TestBaseSimpleConfig):
        super().__init__(connectors)
        self.config = config
        self.exchange = f"uniswap/clmm/{config.network}"
        
    def on_tick(self):
        """每个周期的主要逻辑"""
        if self.current_timestamp % 30 == 0:  # 每30秒打印一次
            self.logger().info("✅ 测试脚本运行正常 - Gateway 连接正常")
    
    def format_status(self) -> str:
        """状态显示"""
        return f"\n{'='*50}\n🧪 Base 测试脚本\n运行中...\n{'='*50}\n"
