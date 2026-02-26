#!/bin/bash
# Pre-flight Check for ETH/USDC LP Trading
# Run this before starting your strategy

echo "🚀 ETH/USDC LP Trading - Pre-flight Check"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_passed=0
check_failed=0

# Check 1: Hummingbot installed
echo -n "1. Checking Hummingbot installation... "
if [ -f "./start" ] && [ -f "./hummingbot/__init__.py" ]; then
    echo -e "${GREEN}✓${NC}"
    ((check_passed++))
else
    echo -e "${RED}✗${NC}"
    echo "   Please install Hummingbot first"
    ((check_failed++))
fi

# Check 2: Gateway connector
echo -n "2. Checking Gateway... "
if command -v docker &> /dev/null; then
    if docker ps | grep -q "gateway"; then
        echo -e "${GREEN}✓${NC}"
        ((check_passed++))
    else
        echo -e "${YELLOW}⚠${NC}"
        echo "   Gateway not running. Run 'docker-compose up -d' or './start'"
        ((check_failed++))
    fi
else
    echo -e "${YELLOW}⚠${NC}"
    echo "   Cannot check - docker not found"
    ((check_failed++))
fi

# Check 3: Script exists
echo -n "3. Checking quick_eth_usdc_lp.py script... "
if [ -f "./scripts/quick_eth_usdc_lp.py" ]; then
    echo -e "${GREEN}✓${NC}"
    ((check_passed++))
else
    echo -e "${RED}✗${NC}"
    echo "   Script not found in scripts/"
    ((check_failed++))
fi

# Check 4: Configuration
echo -n "4. Checking configuration file... "
if [ -f "./conf/scripts/conf_quick_eth_usdc_lp_0.yml" ]; then
    echo -e "${GREEN}✓${NC}"
    ((check_passed++))
else
    echo -e "${YELLOW}⚠${NC}"
    echo "   Config file not found (will be created on first run)"
fi

echo ""
echo "=========================================="
echo -e "Checks passed: ${GREEN}${check_passed}${NC}"
echo -e "Checks failed: ${RED}${check_failed}${NC}"
echo ""

if [ $check_failed -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "📋 Next Steps:"
    echo "1. Start Hummingbot: ./start"
    echo "2. Connect wallet: gateway connect ethereum"
    echo "3. Configure strategy: create --script quick_eth_usdc_lp.py"
    echo "4. Start trading: start --script quick_eth_usdc_lp.py"
    echo ""
    echo "📖 Full guide: QUICK_START_ETH_USDC_LP.md"
else
    echo -e "${RED}⚠ Please fix the issues above before proceeding${NC}"
fi

echo ""
echo "=========================================="
echo ""

# Show current ETH/USDC price (if possible)
echo "💰 Current Market Info:"
echo ""
if command -v curl &> /dev/null; then
    echo "Fetching ETH/USDC price..."
    ETH_PRICE=$(curl -s 'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd' | grep -o '"usd":[0-9.]*' | grep -o '[0-9.]*')
    if [ ! -z "$ETH_PRICE" ]; then
        echo -e "ETH Price: ${GREEN}\$${ETH_PRICE}${NC}"
        
        # Calculate example position value
        if [ ! -z "$ETH_PRICE" ]; then
            ETH_AMOUNT=0.1
            USDC_AMOUNT=300
            ETH_VALUE=$(echo "$ETH_AMOUNT * $ETH_PRICE" | bc)
            TOTAL_VALUE=$(echo "$ETH_VALUE + $USDC_AMOUNT" | bc)
            echo ""
            echo "Example position (0.1 ETH + 300 USDC):"
            echo "  ETH value: \$${ETH_VALUE}"
            echo "  USDC value: \$${USDC_AMOUNT}"
            echo "  Total: \$${TOTAL_VALUE}"
        fi
    fi
fi

echo ""
echo "⚠️  Important Reminders:"
echo "  • Have extra ETH for gas fees (~0.01-0.05 ETH)"
echo "  • Start small while learning"
echo "  • Understand impermanent loss risk"
echo "  • Monitor your position regularly"
echo ""
