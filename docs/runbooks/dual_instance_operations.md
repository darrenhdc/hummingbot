# Dual Instance Operations Runbook（LP + Hyperliquid）

## 1. 适用范围
- 仅用于 `hummingbot` 仓库内双实例运行：
  - LP 实例：`scripts/base_vol_adaptive_lp.py`
  - Perp 实例：`scripts/fgi_llm_hyperliquid_spot.py`
- 本文不涉及 dashboard/subgraph 重构。

## 2. 启动与停止

### 2.1 启动前检查
```bash
cd /Users/darrencui/hummingbot
./start --help
```
- 确认 `.venv310` 存在。
- 确认 `conf/scripts/conf_base_vol_adaptive_lp_0.yml` 参数已更新。
- 确认 `.env` 中 Hyperliquid 相关变量已配置。

### 2.2 启动 LP 实例
```bash
cd /Users/darrencui/hummingbot
./start -f scripts/base_vol_adaptive_lp.py -c conf/scripts/conf_base_vol_adaptive_lp_0.yml > logs/lp_instance.log 2>&1
```

### 2.3 启动 Hyperliquid 实例
```bash
cd /Users/darrencui/hummingbot
./start -f scripts/fgi_llm_hyperliquid_spot.py > logs/hyperliquid_instance.log 2>&1
```

### 2.4 停止实例
- 前台运行：`Ctrl + C`
- 后台运行：
```bash
pkill -f "scripts/base_vol_adaptive_lp.py"
pkill -f "scripts/fgi_llm_hyperliquid_spot.py"
```

## 3. 日常巡检（每日至少 2 次）

### 3.1 Gateway 健康
```bash
cd /Users/darrencui/hummingbot
docker compose ps
```
- 预期：gateway 相关容器为 `Up`。

### 3.2 资金与仓位
- LP：检查策略状态输出中当前价格、区间、仓位状态。
- Perp：检查持仓方向、杠杆、保证金占用。
- 关键风控参数确认：`max_position_pct / min_gas_reserve / stop_loss_pct`。

### 3.3 日志与 Adapter 健康
```bash
tail -n 100 /Users/darrencui/hummingbot/logs/lp_instance.log
tail -n 100 /Users/darrencui/hummingbot/logs/hyperliquid_instance.log
tail -n 20 /Users/darrencui/hummingbot/logs/base_vol_adaptive_lp_events.jsonl
```
- 预期：无连续异常栈；adapter 输出持续更新且字段完整。

## 4. 常见故障处理 SOP

### 4.1 RPC 失败
- 现象：连续出现网络请求失败、pool info 拉取失败。
- 处理：
  1. 检查 RPC 节点可达性（切备份 RPC）。
  2. 重启对应实例。
  3. 观察 5 分钟确认错误消失。

### 4.2 交易超时 / 未确认
- 现象：下单后长时间无成交/无确认。
- 处理：
  1. 暂停策略实例，防止重复下单。
  2. 在链上浏览器核对 tx 状态。
  3. 未上链则重提；已上链待确认则等待或手动加速。

### 4.3 Pending 卡住
- 现象：日志重复 pending，策略不再推进。
- 处理：
  1. 停止实例。
  2. 确认链上实际仓位状态。
  3. 重新启动实例，观察是否恢复心跳和状态迁移。

### 4.4 出区间久不回
- 现象：长时间 out-of-range，反复触发再平衡或收益下降。
- 处理：
  1. 评估当前波动率与区间宽度。
  2. 提高宽度或临时手动平仓观望。
  3. 必要时降低仓位或暂停。

## 5. 紧急流程

### 5.1 紧急停止
```bash
pkill -f "scripts/base_vol_adaptive_lp.py"
pkill -f "scripts/fgi_llm_hyperliquid_spot.py"
```

### 5.2 强制平仓
- 优先通过策略命令触发平仓。
- 若策略失效：直接在 DEX/交易所 UI 手工平仓。

### 5.3 DEX UI 兜底
- 打开官方 DEX UI（如 Uniswap）定位 LP NFT/仓位。
- 执行 Remove Liquidity / Collect Fees。
- 完成后回写运维记录（时间、tx、原因）。
