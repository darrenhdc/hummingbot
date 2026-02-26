#!/bin/bash
# Conda + Hummingbot 快速安装脚本（针对 macOS）

set -e  # 遇到错误立即停止

echo "🚀 Conda + Hummingbot 快速安装"
echo "=============================="
echo ""

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查是否是 macOS
if [ "$(uname)" != "Darwin" ]; then
    echo "❌ 此脚本仅支持 macOS"
    exit 1
fi

# 检查架构
ARCH=$(uname -m)
echo -e "${BLUE}检测到系统架构: ${ARCH}${NC}"

# 步骤 1: 检查/安装 Miniconda
echo ""
echo -e "${BLUE}步骤 1/4: 检查 Conda${NC}"
echo "-------------------"

if command -v conda &> /dev/null; then
    echo -e "  ${GREEN}✅ Conda 已安装${NC}"
    conda --version
else
    echo -e "  ${YELLOW}⚠️  Conda 未安装，开始安装...${NC}"
    
    # 根据架构选择安装包
    if [ "$ARCH" = "arm64" ]; then
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
    else
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh"
    fi
    
    echo "  下载 Miniconda..."
    cd ~
    curl -O $MINICONDA_URL
    
    echo "  安装 Miniconda..."
    bash ~/Miniconda3-latest-MacOSX-*.sh -b -p $HOME/miniconda3
    
    echo "  初始化 conda..."
    $HOME/miniconda3/bin/conda init zsh
    
    # 使 conda 在当前 shell 可用
    export PATH="$HOME/miniconda3/bin:$PATH"
    
    echo -e "  ${GREEN}✅ Miniconda 安装完成${NC}"
    
    # 清理安装文件
    rm ~/Miniconda3-latest-MacOSX-*.sh
fi

# 确保 conda 在 PATH 中
if ! command -v conda &> /dev/null; then
    export PATH="$HOME/miniconda3/bin:$PATH"
fi

# 步骤 2: 安装 Hummingbot 环境
echo ""
echo -e "${BLUE}步骤 2/4: 安装 Hummingbot 环境${NC}"
echo "----------------------------"

cd /Users/handongcui/defi_trading_lab/hummingbot

if conda env list | grep -q "^hummingbot "; then
    echo -e "  ${YELLOW}⚠️  hummingbot 环境已存在，将更新...${NC}"
    ./install
else
    echo "  创建 hummingbot conda 环境..."
    ./install
fi

echo -e "  ${GREEN}✅ Hummingbot 环境安装完成${NC}"

# 步骤 3: 启动 Gateway
echo ""
echo -e "${BLUE}步骤 3/4: 启动 Gateway${NC}"
echo "----------------------"

# 检查 Docker/OrbStack
if ! docker ps &> /dev/null; then
    echo -e "  ${YELLOW}⚠️  Docker 未运行${NC}"
    echo "  尝试启动 OrbStack..."
    
    if [ -d "/Applications/OrbStack.app" ]; then
        open -a OrbStack
        echo "  等待 OrbStack 启动（30秒）..."
        sleep 30
    else
        echo -e "  ${YELLOW}⚠️  请手动启动 Docker Desktop 或 OrbStack${NC}"
        echo "  启动后按 Enter 继续..."
        read
    fi
fi

# 启动 Gateway
if docker ps | grep -q "gateway"; then
    echo -e "  ${GREEN}✅ Gateway 已运行${NC}"
else
    echo "  启动 Gateway 容器..."
    docker-compose up -d gateway
    echo "  等待 Gateway 启动（10秒）..."
    sleep 10
    echo -e "  ${GREEN}✅ Gateway 启动成功${NC}"
fi

# 步骤 4: 完成
echo ""
echo -e "${BLUE}步骤 4/4: 安装完成！${NC}"
echo "--------------------"
echo ""
echo -e "${GREEN}✅ 所有组件安装完成！${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 下一步操作："
echo ""
echo "1️⃣  启动 Hummingbot:"
echo "   ${GREEN}./start${NC}"
echo ""
echo "2️⃣  在 Hummingbot 终端中连接 Base 钱包:"
echo "   ${GREEN}gateway connect base${NC}"
echo "   → 输入: mainnet"
echo "   → 输入: 0x您的私钥..."
echo ""
echo "3️⃣  验证连接:"
echo "   ${GREEN}gateway connector-tokens uniswap base${NC}"
echo ""
echo "4️⃣  启动您的波动率自适应策略:"
echo "   ${GREEN}start --script base_vol_adaptive_lp.py${NC}"
echo ""
echo "5️⃣  查看实时日志（在新终端）:"
echo "   ${GREEN}tail -f logs/logs_script.log${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 完整指南: ${BLUE}BASE_MAINNET_QUICKSTART.md${NC}"
echo "🔐 钱包连接: ${BLUE}WALLET_CONNECTION_GUIDE.md${NC}"
echo ""
echo "⚠️  确保在 Base 网络有:"
echo "   • 0.015+ ETH (0.01 LP + 0.005 gas)"
echo "   • 25+ USDC"
echo ""

# 如果是新安装的 conda，提示重新加载 shell
if [ ! -f "$HOME/.conda_initialized" ]; then
    touch "$HOME/.conda_initialized"
    echo -e "${YELLOW}⚠️  重要: 请重新加载终端配置${NC}"
    echo "   运行: ${GREEN}source ~/.zshrc${NC}"
    echo "   或者关闭并重新打开终端"
    echo ""
fi

echo "🚀 准备好了？运行: ${GREEN}./start${NC}"
echo ""
