# 🚀 Quick Start: ETH/USDC LP Trading on Uniswap V3

Get started with Uniswap V3 liquidity provision in 5 minutes!

## Prerequisites ✅

- [ ] Wallet with ETH (for gas) and USDC/ETH for LP
- [ ] Private key ready
- [ ] Hummingbot installed
- [ ] Gateway running

---

## Step 1: Start Gateway (if not running)

Gateway is required to connect to Uniswap V3.

### Quick Start Gateway:

```bash
# In your hummingbot directory
./start
```

If Gateway isn't installed, run:
```bash
make setup
# Answer 'y' when prompted about Gateway
```

---

## Step 2: Connect Your Wallet

Once Hummingbot is running, connect your Ethereum wallet:

```bash
# In Hummingbot terminal
gateway connect ethereum

# You'll be prompted for:
# 1. Network: mainnet (or goerli for testnet)
# 2. Private Key: Your wallet private key
```

⚠️ **Security Note**: Your private key will be encrypted and stored locally.

### Verify Connection:

```bash
gateway connector-tokens uniswap ethereum

# Should show your ETH and USDC balances
```

---

## Step 3: Create Strategy Configuration

### Option A: Interactive (Recommended for First Time)

```bash
# In Hummingbot terminal
create --script quick_eth_usdc_lp.py
```

You'll be prompted for:
- **Network**: `ethereum` (or `arbitrum`, `optimism`, `polygon`)
- **Trading pair**: `WETH-USDC` (default)
- **ETH amount**: `0.1` (amount of ETH to provide)
- **USDC amount**: `300` (amount of USDC to provide)
- **Range lower %**: `5` (how far below current price)
- **Range upper %**: `5` (how far above current price)
- **Stop loss %**: `10` (close if -10% from entry)
- **Take profit %**: `20` (based on fees collected)
- **Auto-open**: `True` (start position immediately)

### Option B: Edit Config File Directly

Create/edit: `conf/scripts/conf_quick_eth_usdc_lp_0.yml`

```yaml
network: ethereum
trading_pair: WETH-USDC
entry_amount_eth: 0.1
entry_amount_usdc: 300
range_lower_pct: 5
range_upper_pct: 5
stop_loss_pct: 10
take_profit_pct: 20
check_interval: 15
auto_open_position: true
```

---

## Step 4: Start Trading!

```bash
# Start the strategy
start --script quick_eth_usdc_lp.py

# Or if you created a config:
start --script quick_eth_usdc_lp.py --conf conf_quick_eth_usdc_lp_0.yml
```

### Monitor Your Position:

```bash
# Check status
status

# View detailed history
history

# Stop strategy
stop
```

---

## Understanding Your Position

### What the Strategy Does:

1. **Gets Current Price**: Fetches ETH/USDC price from Uniswap V3
2. **Calculates Range**: Creates price range (default ±5%)
3. **Opens Position**: Deposits your ETH+USDC into liquidity pool
4. **Monitors**: Checks price every 15 seconds
5. **Manages Risk**: 
   - Closes if -10% stop loss hit
   - Closes if +20% profit target reached
   - Alerts if price goes out of range

### Example:

Current ETH price: $3,000
- Lower bound: $2,850 (-5%)
- Upper bound: $3,150 (+5%)

Your position earns fees when trades happen in this range!

---

## Advanced Configuration

### Multiple Networks:

```yaml
# Arbitrum (lower gas fees!)
network: arbitrum

# Optimism
network: optimism

# Polygon (very low fees!)
network: polygon
```

### Tighter Range (More fees, more risk):

```yaml
range_lower_pct: 2  # Only 2% below
range_upper_pct: 2  # Only 2% above
```

### Wider Range (Less fees, less risk):

```yaml
range_lower_pct: 10  # 10% below
range_upper_pct: 10  # 10% above
```

---

## Troubleshooting

### "Gateway not connected"
```bash
gateway status
# If not running:
gateway start
```

### "Insufficient ETH for gas"
Make sure you have ~0.01-0.05 ETH extra for gas fees.

### "Pool not found"
- Verify trading pair exists on your selected network
- Check spelling: `WETH-USDC` (not ETH-USDC)

### Check Logs:
```bash
# In hummingbot directory
tail -f logs/logs_script.log
```

---

## Important Notes 📝

### Gas Costs:
- **Mainnet**: ~$50-200 per transaction (open + close)
- **Arbitrum/Optimism**: ~$1-5 per transaction
- **Polygon**: <$1 per transaction

### Impermanent Loss:
- If ETH price moves significantly, you may have less value than just holding
- Fees help offset this, but large price swings = risk
- Best for ranging markets or stable pairs

### Uniswap V3 Fees:
- 0.05% fee tier: Very stable pairs
- 0.3% fee tier: Most common (ETH/USDC default)
- 1% fee tier: More exotic pairs

---

## Quick Commands Reference

```bash
# Check wallet balance
balance

# View current positions
gateway connector-positions uniswap ethereum WETH-USDC

# Stop strategy
stop

# View logs
tail -f logs/logs_script.log

# Get current price
gateway get-price uniswap ethereum WETH-USDC 1
```

---

## Next Steps

After you're comfortable:

1. Try the advanced `uniswap_v3_full_cycle.py` script
2. Experiment with `lp_manage_position.py` for more control
3. Explore other pairs and networks
4. Backtest different range strategies

---

## Getting Help

- Hummingbot Discord: https://discord.gg/hummingbot
- Documentation: https://hummingbot.org
- Gateway Docs: https://hummingbot.org/gateway

---

**Ready to start? Run: `./start` and follow Step 2! 🚀**
