# 🔐 钱包连接完整指南

在运行策略前，您需要先连接钱包到 Hummingbot Gateway。

---

## 📋 前置要求

在开始前，请确保您有：

1. ✅ **Base 网络钱包**
   - MetaMask 或其他 EVM 钱包
   - 钱包私钥（以 0x 开头的 64 位字符串）

2. ✅ **Base 网络资金**
   - 至少 0.015 ETH（0.01 用于 LP + 0.005 gas 费）
   - 至少 25 USDC

3. ⚠️ **安全建议**
   - 使用专门的测试钱包
   - 不要使用存有大额资金的主钱包

---

## 🚀 完整连接流程

### 第一步：启动 Docker（OrbStack）

您的系统使用 OrbStack，需要先启动它：

#### macOS 启动 OrbStack

1. **打开 Finder**
2. **进入 Applications（应用程序）**
3. **找到并双击 OrbStack**
4. **等待 OrbStack 图标出现在菜单栏** ⚡

或者使用命令启动：

```bash
open -a OrbStack
```

#### 验证 OrbStack 运行

```bash
docker ps
```

**预期输出**：显示容器列表（可能为空，这是正常的）

如果显示错误，说明 OrbStack 还没完全启动，等待 30 秒后重试。

---

### 第二步：启动 Gateway

Gateway 是连接 Hummingbot 和区块链的桥梁。

#### 2.1 检查 Gateway 配置

```bash
# 确认在 hummingbot 目录
cd /Users/handongcui/defi_trading_lab/hummingbot

# 检查配置文件
ls docker-compose.yml
```

#### 2.2 启动 Gateway

```bash
docker-compose up -d gateway
```

**预期输出**：
```
Creating network "hummingbot_default" with the default driver
Creating hummingbot_gateway_1 ... done
```

#### 2.3 验证 Gateway 运行

```bash
# 查看 Gateway 容器
docker ps | grep gateway
```

**预期输出**：应该看到一行包含 `gateway` 的信息

#### 2.4 等待 Gateway 启动完成

```bash
# 等待 5-10 秒
sleep 10

# 查看 Gateway 日志（可选）
docker-compose logs gateway
```

---

### 第三步：启动 Hummingbot

```bash
# 在 hummingbot 目录下
./start
```

**预期输出**：Hummingbot 启动界面

```
    .__                          ___.           __   
    |  |__  __ __  _____   _____ \_ |__   _____/  |_ 
    |  |  \|  |  \/     \ /     \ | __ \ /  _ \   __\
    |   Y  \  |  /  Y Y  \  Y Y  \| \_\ (  <_> )  |  
    |___|  /____/|__|_|  /__|_|  /|___  /\____/|__|  
         \/            \/      \/     \/             

Version: ...
```

---

### 第四步：连接 Base 钱包

#### 4.1 在 Hummingbot 终端中执行

```bash
gateway connect base
```

#### 4.2 按提示输入信息

**提示 1: 选择网络**
```
Which network do you want to connect to? (mainnet/testnet)
>>> mainnet
```

**提示 2: 输入私钥**
```
Enter your Base wallet private key
>>> 0x您的私钥（64位十六进制字符）
```

⚠️ **如何获取私钥？**

**MetaMask 用户**：
1. 打开 MetaMask
2. 点击右上角的三个点
3. 选择 "Account Details"（账户详情）
4. 点击 "Export Private Key"（导出私钥）
5. 输入密码
6. 复制私钥（以 0x 开头）

**预期输出**：
```
✅ Successfully connected to base mainnet
```

---

### 第五步：验证连接

#### 5.1 检查 Gateway 状态

```bash
gateway status
```

**预期输出**：
```
Gateway Status
==============
Gateway:   online
Networks:  base (mainnet) ✓
```

#### 5.2 检查钱包余额

```bash
gateway connector-tokens uniswap base
```

**预期输出**：
```
Token Balances (base mainnet)
=============================
WETH:  0.0234 
USDC:  142.50
ETH:   0.0150
```

如果余额不足：
- ETH < 0.015 → 需要充值
- USDC < 25 → 需要充值

#### 5.3 使用 Hummingbot balance 命令

```bash
balance
```

**预期输出**：显示所有已连接网络的余额

---

### 第六步：启动策略

#### 6.1 启动 Base 波动率自适应策略

```bash
start --script base_vol_adaptive_lp.py
```

#### 6.2 预期行为

策略将：
1. ✓ 获取当前 ETH/USDC 价格
2. ✓ 计算动态区间
3. ✓ 自动开仓（0.01 ETH + 25 USDC）
4. ✓ 开始监控

#### 6.3 查看实时日志

**在新终端窗口**：

```bash
cd /Users/handongcui/defi_trading_lab/hummingbot
tail -f logs/logs_script.log
```

---

## 🔧 常见问题排查

### 问题 1: "Docker daemon not running"

**原因**: OrbStack/Docker 未启动

**解决**:
```bash
# 启动 OrbStack
open -a OrbStack

# 等待 30 秒
sleep 30

# 验证
docker ps
```

---

### 问题 2: "Gateway not connected"

**原因**: Gateway 容器未运行

**解决**:
```bash
# 启动 Gateway
docker-compose up -d gateway

# 等待启动完成
sleep 10

# 验证
docker ps | grep gateway
```

---

### 问题 3: "Invalid private key"

**原因**: 私钥格式不正确

**检查**:
- ✓ 必须以 `0x` 开头
- ✓ 后面跟着 64 位十六进制字符（0-9, a-f）
- ✓ 总长度 66 个字符（0x + 64位）

**正确格式示例**:
```
0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
```

---

### 问题 4: "Insufficient balance"

**原因**: Base 网络余额不足

**解决**:

#### 方法 1: 从 Ethereum 主网桥接

1. 访问: https://bridge.base.org
2. 连接 MetaMask
3. 选择 "Ethereum → Base"
4. 桥接至少 0.02 ETH
5. 等待 5-10 分钟

#### 方法 2: 从交易所提现

支持 Base 网络的交易所（部分）：
- Coinbase（原生支持）
- Binance
- OKX

提现时选择 "Base" 网络

#### 方法 3: 使用 Uniswap 兑换

如果已经有 ETH：
1. 访问: https://app.uniswap.org
2. 切换到 Base 网络
3. 用部分 ETH 换成 USDC（至少 25 USDC）

---

### 问题 5: "Cannot connect to pool"

**原因**: RPC 连接问题

**解决**:
```bash
# 重启 Gateway
docker-compose restart gateway

# 等待 10 秒
sleep 10

# 重新连接
gateway connect base
```

---

## 📝 完整命令速查

### 启动流程

```bash
# 1. 启动 OrbStack
open -a OrbStack && sleep 30

# 2. 启动 Gateway
docker-compose up -d gateway && sleep 10

# 3. 启动 Hummingbot
./start

# 4. 在 Hummingbot 中：
gateway connect base
# → 输入 mainnet
# → 输入私钥

# 5. 验证
gateway connector-tokens uniswap base

# 6. 启动策略
start --script base_vol_adaptive_lp.py
```

### 检查命令

```bash
# 检查 Docker
docker ps

# 检查 Gateway 日志
docker-compose logs gateway

# 检查 Hummingbot 日志  
tail -f logs/logs_script.log

# 检查策略状态
status
```

### 停止命令

```bash
# 停止策略
stop

# 停止 Hummingbot
exit

# 停止 Gateway
docker-compose down
```

---

## 🎯 快速启动（一键复制）

如果一切正常，直接复制粘贴这些命令：

```bash
# 确保在正确目录
cd /Users/handongcui/defi_trading_lab/hummingbot

# 启动 OrbStack（如果未运行）
open -a OrbStack

# 等待 Docker 启动
echo "等待 Docker 启动..." && sleep 30

# 启动 Gateway
docker-compose up -d gateway

# 等待 Gateway 准备就绪
echo "等待 Gateway 启动..." && sleep 10

# 验证 Gateway
docker ps | grep gateway

# 启动 Hummingbot
./start
```

**然后在 Hummingbot 终端执行**：

```bash
gateway connect base
# 输入: mainnet
# 输入: 0x您的私钥

gateway connector-tokens uniswap base
start --script base_vol_adaptive_lp.py
```

---

## ✅ 连接成功标志

当您看到以下内容，说明连接成功：

```
🚀 Base Mainnet 波动率自适应 LP 策略已启动
💰 测试金额: 0.01 ETH + 25 USDC
📊 区间范围: 1.50% - 4.00%
📊 Base ETH/USDC 当前价格: $1,970.95
🎯 开始开仓...
📍 开仓区间: $1,931.33 - $2,010.57
✅ 开仓成功! Order ID: ...
💰 开仓价格: $1,970.95
```

---

## 📞 需要帮助？

如果遇到问题：

1. **查看日志**
   ```bash
   tail -100 logs/logs_script.log
   ```

2. **检查 Gateway 日志**
   ```bash
   docker-compose logs gateway | tail -50
   ```

3. **重启所有服务**
   ```bash
   docker-compose down
   docker-compose up -d gateway
   ./start
   ```

4. **社区支持**
   - Hummingbot Discord: https://discord.gg/hummingbot
   - GitHub Issues: https://github.com/hummingbot/hummingbot

---

**准备好了？开始连接您的钱包！🚀**
