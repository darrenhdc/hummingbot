# Go-Live Checklist（上线前检查）

## 1. 风控参数确认（必填）
- [ ] `max_position_pct` 已确认且 `<= 50`
- [ ] `min_gas_reserve` 已确认且与当前网络 gas 成本匹配
- [ ] `stop_loss_pct` 已确认且在可接受风险范围内
- [ ] 参数变更已留痕（提交记录/变更单）

## 2. 钱包与资金隔离确认（LP 与 Perp）
- [ ] LP 与 Hyperliquid 使用隔离资金口径（避免互相挤占）
- [ ] 关键私钥/凭证来源确认（无明文泄露）
- [ ] 可用余额与计划仓位匹配

## 3. 日志与 Adapter 输出健康检查
- [ ] `logs/lp_instance.log` 最近 100 行无连续异常
- [ ] `logs/hyperliquid_instance.log` 最近 100 行无连续异常
- [ ] `logs/base_vol_adaptive_lp_events.jsonl` 持续输出且字段完整：
  - `strategy_id, timestamp, action, reason, price, range_lower, range_upper, in_range, fees_collected, estimated_il_pct, gas_cost`

## 4. 回滚预案与责任人

### 4.1 回滚预案
- [ ] 回滚目标版本（commit/tag）：`__________`
- [ ] 回滚命令已演练：`git checkout <target>` 或部署回滚脚本
- [ ] 紧急停机命令已验证：
  - `pkill -f "scripts/base_vol_adaptive_lp.py"`
  - `pkill -f "scripts/fgi_llm_hyperliquid_spot.py"`

### 4.2 联系人与责任人
- 值班负责人（Owner）：`__________`
- 交易风控负责人：`__________`
- 基础设施负责人：`__________`
- 升级审批人：`__________`

## 5. 上线判定规则（Go / No-Go）

### Go（可上线）
满足以下全部条件：
1. 本文第 1~4 节检查项全部勾选；
2. 回归测试通过；
3. 无未关闭的 P0/P1 风险项。

### No-Go（不可上线）
任一条件触发即不可上线：
1. 任一风控参数缺失或越界；
2. adapter 输出字段不完整或持续中断；
3. 无明确回滚负责人或回滚步骤未验证；
4. 关键演练（gateway/tx/gas/OOR）未完成。
