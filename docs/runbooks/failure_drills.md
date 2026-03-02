# Failure Drills（最小可复现）

## 演练总规则
- 演练前：确认小资金/测试仓位。
- 演练中：记录触发时间、日志片段、恢复时间。
- 演练后：必须执行恢复步骤并通过验收标准。

---

## Drill-A：Gateway 不可用

### 触发方式
```bash
cd /Users/darrencui/hummingbot
docker compose stop gateway
```

### 预期行为
- LP 脚本出现 pool/gateway 请求失败日志。
- 不应继续成功开仓。

### 恢复步骤
```bash
cd /Users/darrencui/hummingbot
docker compose start gateway
```
- 重启 LP 实例并观察 3~5 分钟。

### 验收标准
- gateway 容器恢复 `Up`。
- LP 实例恢复正常轮询，无连续错误栈。

---

## Drill-B：交易超时 / 未确认

### 触发方式（测试步骤）
1. 在低流动性或拥堵时段提交小额开仓。
2. 观察链上 tx 持续 pending（或故意短时断网后恢复）。

### 预期行为
- 策略不应无限制重复提交同类交易。
- 日志可见 pending/等待确认信息。

### 恢复步骤
1. 暂停实例，避免叠单。
2. 区块浏览器确认 tx：
   - 未上链：重提。
   - 已上链 pending：手工加速或等待确认。
3. 交易状态明确后重启实例。

### 验收标准
- 无重复叠单。
- 实例恢复后状态可继续推进。

---

## Drill-C：Gas Reserve 不足

### 触发方式
将 `conf/scripts/conf_base_vol_adaptive_lp_0.yml` 中 `min_gas_reserve` 临时调高到高于钱包实际余额（例如 `1.0`）。

### 预期行为
- 开仓被硬拦截。
- adapter 输出 `action=hold`, `reason=gas_reserve_insufficient`。

### 恢复步骤
1. 将 `min_gas_reserve` 调回合理值。
2. 或补充 gas token 余额。
3. 重启 LP 实例。

### 验收标准
- 恢复后可正常通过开仓前风控。

---

## Drill-D：Out-of-Range 持续触发

### 触发方式（测试步骤）
1. 使用较窄区间参数运行 LP（如低 `fallback_width_bps`）。
2. 在波动较大时段运行，观察频繁 OOR。

### 预期行为
- 触发 `rebalance` 事件并记录 adapter 输出。
- 若达到止损条件，走 stop-loss 平仓路径。

### 恢复步骤
1. 扩大区间参数或降低仓位。
2. 必要时手动平仓并暂停观察。

### 验收标准
- OOR 事件可观测、可恢复。
- 参数调整后重平衡频次下降。
