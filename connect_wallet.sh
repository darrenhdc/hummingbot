#!/bin/bash
# 钱包连接快速指南

echo "🔐 Hummingbot Base 钱包连接指南"
echo "================================"
echo ""

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ 未找到 docker-compose.yml"
    echo "   请先运行: make setup"
    exit 1
fi

echo "步骤 1: 启动 Docker"
echo "-------------------"
echo ""

# Check if OrbStack or Docker is running
if pgrep -x "OrbStack" > /dev/null; then
    echo "✅ OrbStack 已运行"
elif pgrep -x "Docker" > /dev/null; then
    echo "✅ Docker Desktop 已运行"
else
    echo "⚠️  Docker 未运行，请先启动："
    echo ""
    echo "   macOS 用户："
    echo "   - 如果使用 OrbStack: 打开 OrbStack 应用"
    echo "   - 如果使用 Docker Desktop: 打开 Docker Desktop"
    echo ""
    echo "   启动后按 Enter 继续..."
    read
fi

echo ""
echo "步骤 2: 启动 Gateway"
echo "-------------------"
echo ""

# Try to start gateway
if docker-compose ps | grep -q "gateway"; then
    echo "✅ Gateway 已运行"
else
    echo "🚀 正在启动 Gateway..."
    docker-compose up -d gateway
    
    if [ $? -eq 0 ]; then
        echo "✅ Gateway 启动成功"
        echo "   等待 5 秒让服务完全启动..."
        sleep 5
    else
        echo "❌ Gateway 启动失败"
        echo "   请检查 docker-compose.yml 配置"
        exit 1
    fi
fi

echo ""
echo "步骤 3: 准备钱包信息"
echo "-------------------"
echo ""

echo "您需要准备："
echo "  1️⃣  钱包私钥 (0x...)"
echo "  2️⃣  确认在 Base 网络有资金："
echo "      - 0.015+ ETH (0.01 LP + 0.005 gas)"
echo "      - 25+ USDC"
echo ""

echo "⚠️  安全提醒："
echo "  • 建议使用专门的测试钱包"
echo "  • 不要使用存有大额资金的主钱包"
echo "  • 私钥会被加密存储在本地"
echo ""

echo "步骤 4: 启动 Hummingbot 并连接钱包"
echo "-----------------------------------"
echo ""

echo "现在请执行："
echo ""
echo "  1. 启动 Hummingbot:"
echo "     ./start"
echo ""
echo "  2. 在 Hummingbot 终端中连接 Base 钱包:"
echo "     gateway connect base"
echo ""
echo "  3. 按提示输入："
echo "     - 网络: mainnet"
echo "     - 私钥: 0x您的私钥..."
echo ""
echo "  4. 验证连接:"
echo "     gateway connector-tokens uniswap base"
echo ""
echo "  5. 查看余额:"
echo "     balance"
echo ""
echo "  6. 启动策略:"
echo "     start --script base_vol_adaptive_lp.py"
echo ""

echo "================================"
echo "准备好了吗？"
echo ""
echo "按 Enter 启动 Hummingbot，或 Ctrl+C 退出"
read

# Start hummingbot
if [ -f "./start" ]; then
    echo "🚀 启动 Hummingbot..."
    ./start
else
    echo "❌ ./start 文件未找到"
    echo "   请确认您在 hummingbot 目录下"
fi
