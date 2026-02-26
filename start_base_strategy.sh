#!/bin/bash
# Base Mainnet 快速启动脚本

echo "🚀 Base Mainnet 波动率自适应 LP 策略"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}步骤 1/5: 检查文件${NC}"
echo ""

# Check strategy file
if [ -f "./scripts/base_vol_adaptive_lp.py" ]; then
    echo -e "  ✅ 策略文件: ${GREEN}base_vol_adaptive_lp.py${NC}"
else
    echo -e "  ❌ 策略文件未找到"
    exit 1
fi

# Check config file
if [ -f "./conf/scripts/conf_base_vol_adaptive_lp_0.yml" ]; then
    echo -e "  ✅ 配置文件: ${GREEN}conf_base_vol_adaptive_lp_0.yml${NC}"
else
    echo -e "  ❌ 配置文件未找到"
    exit 1
fi

echo ""
echo -e "${BLUE}步骤 2/5: 检查 Gateway${NC}"
echo ""

if command -v docker &> /dev/null; then
    if docker ps | grep -q "gateway"; then
        echo -e "  ✅ Gateway 运行中"
    else
        echo -e "  ${YELLOW}⚠️  Gateway 未运行${NC}"
        echo "     运行: docker-compose up -d"
    fi
else
    echo -e "  ${YELLOW}⚠️  无法检查 Docker${NC}"
fi

echo ""
echo -e "${BLUE}步骤 3/5: 配置概览${NC}"
echo ""

echo "  📊 交易对: WETH-USDC (Base mainnet)"
echo "  💰 金额: 0.01 ETH + 25 USDC (~$45-50)"
echo "  📈 区间: 动态调整 (1.5% - 4%)"
echo "  ⏱️  检查: 每 30 秒"
echo ""

# Show current ETH price
echo -e "${BLUE}步骤 4/5: 市场信息${NC}"
echo ""

if command -v curl &> /dev/null; then
    ETH_PRICE=$(curl -s 'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd' | grep -o '"usd":[0-9.]*' | grep -o '[0-9.]*')
    if [ ! -z "$ETH_PRICE" ]; then
        echo -e "  💵 ETH 价格: ${GREEN}\$$ETH_PRICE${NC}"
        
        # Calculate position value
        ETH_AMOUNT=0.01
        USDC_AMOUNT=25
        ETH_VALUE=$(echo "$ETH_AMOUNT * $ETH_PRICE" | bc)
        TOTAL_VALUE=$(echo "$ETH_VALUE + $USDC_AMOUNT" | bc)
        
        echo "  💰 仓位价值: $${TOTAL_VALUE}"
        echo ""
    fi
fi

echo -e "${BLUE}步骤 5/5: 启动指令${NC}"
echo ""

echo "准备好开始了吗？请在 Hummingbot 终端中执行："
echo ""
echo -e "${GREEN}  1. gateway connect base${NC}"
echo -e "${GREEN}  2. start --script base_vol_adaptive_lp.py${NC}"
echo ""

echo "查看实时日志（在新终端）："
echo -e "${GREEN}  tail -f logs/logs_script.log${NC}"
echo ""

echo "========================================"
echo ""
echo "⚠️  重要提醒："
echo "  • 确保在 Base 网络有 0.015+ ETH"
echo "  • 确保有 25+ USDC"
echo "  • 首次使用建议用测试钱包"
echo "  • Base gas 费很低 (~$0.01-0.10/tx)"
echo ""
echo "📖 完整指南: BASE_MAINNET_QUICKSTART.md"
echo ""

# Ask if user wants to see detailed guide
echo "需要查看详细指南吗? [y/N]"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    if [ -f "BASE_MAINNET_QUICKSTART.md" ]; then
        cat BASE_MAINNET_QUICKSTART.md | less
    else
        echo "指南文件未找到"
    fi
fi

echo ""
echo "🚀 准备好了？启动 Hummingbot: ./start"
echo ""
