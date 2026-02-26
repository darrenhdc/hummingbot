# 🚀 Base Mainnet 快速上手指南

将您的波动率自适应策略部署到 Base mainnet，小额测试！

---

## 📋 您的策略已准备好

✅ **策略文件**: `scripts/base_vol_adaptive_lp.py`
✅ **配置文件**: `conf/scripts/conf_base_vol_adaptive_lp_0.yml`
✅ **测试金额**: 0.01 ETH + 25 USDC (约 $45-50)

---

## 🎯 核心策略逻辑（来自您的 strategy_000）

```
在区间内 → 保持不动（HOLD）
出区间   → 重新平衡（REBALANCE）
         ↓
     根据波动率计算新区间
         ↓
     关闭旧仓位 → 开新仓位
```

**动态区间计算**：
- 波动率高 → 区间宽（最多 4%）→ 更安全，减少重新平衡
- 波动率低 → 区间窄（最少 1.5%）→ 更多手续费收入

---

## 🔧 第一步：配置 Base Network

### 1.1 启动 Hummingbot

```bash
cd /Users/handongcui/defi_trading_lab/hummingbot
./start
```

### 1.2 连接 Base Mainnet 钱包

在 Hummingbot 终端中：

```bash
gateway connect base
```

**提示**：
1. 选择网络: `mainnet`
2. 输入私钥: `0x您的私钥...`

⚠️ **重要**：请使用专门用于测试的钱包，不要用存有大额资金的主钱包！

### 1.3 验证连接

```bash
gateway connector-tokens uniswap base
```

**预期输出**：显示您在 Base 上的 ETH 和 USDC 余额

---

## 💰 第二步：准备测试资金

### 2.1 检查余额

确保您的 Base 钱包有：
- ✅ **0.015+ ETH** (0.01 用于 LP + 0.005 gas 费)
- ✅ **25+ USDC** (25 用于 LP)

### 2.2 如何将资金转入 Base？

**选项 A：从主网桥接（推荐）**
1. 访问 Base 官方桥: https://bridge.base.org
2. 连接钱包
3. 从 Ethereum 桥接少量 ETH → Base
4. 在 Base 上通过 Uniswap 换一些 USDC

**选项 B：从交易所提现**
某些交易所（如 Coinbase）支持直接提现到 Base 网络

### 2.3 验证资金

```bash
# 在 Hummingbot 中
balance

# 或使用 Gateway
gateway connector-tokens uniswap base
```

---

## 🎬 第三步：启动策略（一键启动！）

### 3.1 直接启动（使用预设配置）

```bash
start --script base_vol_adaptive_lp.py
```

**自动执行**：
1. ✓ 获取当前 ETH/USDC 价格
2. ✓ 计算动态区间宽度（根据波动率）
3. ✓ 自动开仓（0.01 ETH + 25 USDC）
4. ✓ 开始监控（每 30 秒检查一次）

### 3.2 查看实时状态

```bash
status
```

**输出示例**：
```
🎯 Base Mainnet 波动率自适应 LP 策略
==========================================
当前价格: $1,961.84
重新平衡次数: 0

📍 仓位状态: ✅ 在区间内
区间: $1,922.40 - $2,001.28
宽度: 2.00%
==========================================
```

---

## 📊 第四步：监控和管理

### 4.1 实时日志

在新终端窗口查看详细日志：

```bash
cd /Users/handongcui/defi_trading_lab/hummingbot
tail -f logs/logs_script.log
```

**关键日志**：
- `📊 当前价格` - 实时价格
- `✅ 在区间内` - 策略保持不动
- `⚠️ 价格已出区间` - 触发重新平衡
- `🔄 开始重新平衡` - 正在调整仓位

### 4.2 手动命令

```bash
# 查看历史
history

# 查看余额
balance

# 检查仓位
gateway connector-positions uniswap base WETH-USDC

# 停止策略
stop
```

---

## 🔄 策略运行流程

### 正常运行场景

```
时间 00:00 - 开仓
  ├─ 价格: $2,000
  ├─ 计算区间: ±2% ($1,960 - $2,040)
  └─ 开仓成功 ✅

时间 00:30 - 第 1 次检查
  ├─ 价格: $2,010 (在区间内)
  └─ 动作: 保持不动 ✅

时间 01:00 - 第 2 次检查
  ├─ 价格: $2,030 (在区间内)
  └─ 动作: 保持不动 ✅

时间 01:30 - 第 3 次检查
  ├─ 价格: $2,050 (超出上限!)
  ├─ 触发: 重新平衡
  ├─ 关闭旧仓位
  ├─ 重新计算区间: ±2% ($2,009 - $2,091)
  └─ 开新仓位 ✅
```

### 重新平衡触发条件

只有一个条件：**价格出区间**
- 价格 < 下限 → 立即重新平衡
- 价格 > 上限 → 立即重新平衡

---

## 🎛️ 调整参数（可选）

### 5.1 编辑配置文件

```bash
nano conf/scripts/conf_base_vol_adaptive_lp_0.yml
```

### 5.2 关键参数说明

```yaml
# 💰 资金量
entry_amount_eth: 0.01     # 增加到 0.02 = 更大仓位
entry_amount_usdc: 25      # 增加到 50 = 更大仓位

# 📊 区间宽度范围
w_min: 150                 # 降低 = 更窄区间 = 更多手续费（但更频繁重新平衡）
w_max: 400                 # 提高 = 更宽区间 = 更安全（但手续费更少）

# ⏱️ 检查频率
check_interval: 30         # 降低 = 更频繁检查（更快响应）
                           # 提高 = 更不频繁（减少系统负担）
```

### 5.3 重启策略

```bash
# 在 Hummingbot 中
stop
start --script base_vol_adaptive_lp.py
```

---

## 🚨 重要注意事项

### Base Network 特点

✅ **优势**：
- 🌟 Gas 费极低（~$0.01-0.10 per tx）
- ⚡ 确认速度快（2-5 秒）
- 🏦 Coinbase 支持，资金进出方便
- 📈 流动性不错（Uniswap V3 主要 DEX）

⚠️ **注意**：
- Base 是 L2，与 Ethereum mainnet 不同
- 需要通过桥接转移资金
- 确认交易所支持 Base 网络提现

### Gas 费预算

| 操作 | 预计 Gas 费 |
|-----|-----------|
| 开仓 | $0.05-0.10 |
| 平仓 | $0.05-0.10 |
| 重新平衡 | $0.10-0.20 |

**总预留**: 0.005 ETH (~$10) 足够进行 50+ 次操作

---

## 🧪 测试计划建议

### Phase 1: 观察期（第 1 天）
- 🎯 目标：验证策略逻辑正确
- 📝 任务：观察是否正确响应价格变动
- ✅ 成功标准：出区间时能正确重新平衡

### Phase 2: 优化期（第 2-3 天）
- 🎯 目标：调整参数提高收益
- 📝 任务：记录重新平衡频率，调整区间宽度
- ✅ 成功标准：重新平衡次数合理（<5次/天）

### Phase 3: 扩展期（第 4-7 天）
- 🎯 目标：增加仓位，长期运行
- 📝 任务：将金额增加到 0.05-0.1 ETH
- ✅ 成功标准：实现正收益（手续费 > gas 费）

---

## 📈 性能评估

### 计算实际收益

```python
# 每天记录
初始投入 = 0.01 ETH + 25 USDC ~= $45-50
当前价值 = (查看仓位) ~= $?
累计手续费 = (查看仓位详情)
累计 Gas 费 = 重新平衡次数 × $0.15

净收益 = (当前价值 + 累计手续费) - 初始投入 - 累计 Gas 费
ROI = 净收益 / 初始投入 × 100%
```

### 目标基准（Base 上 ETH/USDC LP）

| 期望 | 日收益率 | 年化 APY |
|-----|---------|---------|
| 优秀 | >0.2% | >73% |
| 良好 | 0.1-0.2% | 36-73% |
| 及格 | 0.05-0.1% | 18-36% |
| 需调整 | <0.05% | <18% |

---

## 🛠️ 常见问题

### Q1: "Gateway not connected"

```bash
gateway status
# 如果未运行
gateway start

# 重新连接
gateway connect base
```

### Q2: "Insufficient balance"

检查：
1. 是否在 **Base** 网络（不是 Ethereum）
2. 是否有足够的 ETH 和 USDC
3. 是否预留了 gas 费

```bash
gateway connector-tokens uniswap base
```

### Q3: 策略一直重新平衡怎么办？

可能是区间太窄，编辑配置：

```yaml
w_min: 200  # 从 150 增加到 200
w_max: 500  # 从 400 增加到 500
fallback_width_bps: 300  # 从 200 增加到 300
```

### Q4: 如何手动关闭仓位？

**方法 1**：在 Hummingbot 中停止策略
```bash
stop
```
然后手动访问 Uniswap 界面关闭

**方法 2**：直接在 Uniswap 界面
1. 访问: https://app.uniswap.org
2. 切换到 Base 网络
3. 连接钱包
4. Pools → Close Position

---

## 📞 获取帮助

### 查看日志
```bash
tail -f logs/logs_script.log
```

### 检查详细错误
```bash
# 最近 100 行日志
tail -100 logs/logs_script.log | grep ERROR
```

### 社区支持
- Hummingbot Discord: https://discord.gg/hummingbot
- Base Discord: https://discord.gg/base

---

## ✅ 快速启动检查清单

在执行前确认：

- [ ] Hummingbot 已安装并运行
- [ ] Gateway 连接 Base mainnet
- [ ] 钱包有足够资金（0.015 ETH + 25 USDC）
- [ ] 策略文件已创建（`scripts/base_vol_adaptive_lp.py`）
- [ ] 配置文件已创建（`conf/scripts/conf_base_vol_adaptive_lp_0.yml`）
- [ ] 已理解重新平衡逻辑（出区间 → 重开仓位）

**全部确认？执行：**

```bash
./start
gateway connect base
start --script base_vol_adaptive_lp.py
```

---

## 🚀 准备好了？

执行下面的命令开始：

```bash
# 1. 进入目录
cd /Users/handongcui/defi_trading_lab/hummingbot

# 2. 启动 Hummingbot
./start

# 3. 在 Hummingbot 终端中连接 Base
gateway connect base

# 4. 启动策略
start --script base_vol_adaptive_lp.py

# 5. 在新终端查看日志
tail -f logs/logs_script.log
```

**祝交易顺利！🎉**

---

## 📊 相关文档

- [TRADING_RULES_CN.md](TRADING_RULES_CN.md) - 完整交易规则
- [QUICK_REFERENCE.txt](QUICK_REFERENCE.txt) - 命令速查
- [AGENTS.md](AGENTS.md) - AI 助手指令

Base 上见！⚡️
