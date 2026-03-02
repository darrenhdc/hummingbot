# Migration Parity Checklist（WP-1 Baseline Mapping）

## 判定标准
- `mapped`：Target 中已存在可直接对照的实现入口（方法/模块）。
- `unmapped`：Target 中缺失，或仅部分相似（按保守口径一律记为 `unmapped`）。

## 假设
1. WP-1 仅做静态映射与差异识别，不改动交易逻辑。
2. “部分实现”不计为对齐，避免高估迁移完成度。
3. 外部分析栈（dashboard/subgraph/API）在 Phase 1 可外置保留；若 Target 仓库内缺失，仍记录为 `unmapped`。

## 功能对照清单

| 功能项 | Baseline位置 | Target位置 | 状态(mapped/unmapped) | 备注 |
|---|---|---|---|---|
| FSM决策入口（full-cycle） | `strategies/strategy_001_full_cycle/strategy.py:68 (decide)` | `scripts/uniswap_v3_full_cycle.py:168 (_tick_async)` | mapped | 均由周期性检查驱动决策。 |
| Idle且无仓位时入场判定 | `strategy_001...:85,104 (_maybe_open_entry)` | `uniswap_v3_full_cycle.py:223-227 (_handle_no_position/_open_entry)` | mapped | 入场区间过滤均存在。 |
| Entry阶段触及下沿缓冲后平仓 | `strategy_001...:219,235 (_handle_entry_phase)` | `uniswap_v3_full_cycle.py:244-261 (_handle_position/_close_position)` | mapped | `reason=lower` 后进入待保本开仓阶段。 |
| await_breakeven_open 价格回到下沿上方则放弃保本并回idle | `strategy_001...:162,179` | `uniswap_v3_full_cycle.py:230-240` | mapped | 行为一致。 |
| await_breakeven_open 开保本仓 | `strategy_001...:162 (_maybe_open_breakeven)` | `uniswap_v3_full_cycle.py:241,301 (_open_breakeven)` | mapped | 保本区间开仓路径存在。 |
| Breakeven阶段触发平仓回idle | `strategy_001...:255,264 (_handle_breakeven_phase)` | `uniswap_v3_full_cycle.py:263-270` | mapped | 价格达到保本目标后退出。 |
| 未知phase恢复到idle | `strategy_001...:97-102 (Unknown phase reset)` | `N/A` | unmapped | Target 未见显式 unknown-phase 兜底恢复逻辑。 |
| 平仓后计算P_BE并写入状态 | `strategy_001...:408 (on_position_closed)` | `uniswap_v3_full_cycle.py:344-400 (did_fill_order/_compute_breakeven_after_close)` | mapped | 均在下沿触发平仓后计算保本价。 |
| Pool liquidity为0时跳过决策 | `strategy_001...:69` | `N/A` | unmapped | Target full-cycle 未见 `pool_liquidity==0` 守卫。 |
| Tick对齐与价格-Tick双向换算 | `strategy_001...:279-366` | `N/A` | unmapped | Target 脚本直接按价格下单，未见显式 tick 对齐层。 |
| 闭环资本模型（capital_usdc/last_close_value_usdc） | `strategy_001...:124-135,190-200` | `uniswap_v3_full_cycle.py:403-412 (_wallet_amounts)` | unmapped | Target 采用余额百分比，不等价于 baseline 闭环资金口径。 |
| Vol-adaptive决策入口 | `strategies/strategy_000_vol_adaptive/strategy.py:54` | `scripts/base_vol_adaptive_lp.py:299 (_monitor_position)` | mapped | 都以周期检查驱动。 |
| 在区间内保持不动 | `strategy_000...:62` | `base_vol_adaptive_lp.py:324-326` | mapped | 行为一致。 |
| 出区间触发再平衡 | `strategy_000...:89 (REBALANCE)` | `base_vol_adaptive_lp.py:255-287 (_rebalance_position)` | mapped | 均执行 close→open 的再平衡动作。 |
| realized_vol_7d 波动率接入 | `strategy_000...:72` | `base_vol_adaptive_lp.py:186-193 (TODO)` | unmapped | Target 尚未接入真实波动率数据源。 |
| 波动率失效时fallback宽度 | `strategy_000...:86-87` | `base_vol_adaptive_lp.py:204-208` | mapped | fallback宽度逻辑存在。 |
| 无仓位时直接HOLD（000策略） | `strategy_000...:55` | `base_vol_adaptive_lp.py:148-150 (auto_open_position)` | unmapped | Target 默认可自动开仓，行为不一致。 |
| 统一ActionType调度（OPEN/CLOSE/REBALANCE） | `src/bot.py:4772-4911,5249-5264` | `scripts/uniswap_v3_full_cycle.py` / `scripts/base_vol_adaptive_lp.py` | unmapped | Target 为脚本内命令式调用，无独立 `StrategyDecision` 调度层。 |
| 无state但可执行phase时仍触发循环 | `src/watcher.py:114-125,293-302` | `N/A` | unmapped | Target 无外置 `strategy_state.json`+watcher 同等机制。 |
| 交易发送互斥锁（防nonce冲突） | `src/bot.py:1017 (_TxSendLock)` | `N/A` | unmapped | Target脚本层未见等价锁机制。 |
| Gas价格上限守卫 | `src/bot.py:2175-2177` | `N/A` | unmapped | Target脚本未实现 `max_gas_gwei` 守卫。 |
| 配置中心（active_strategy + params） | `config/strategy.yaml:1-56` | `conf/scripts/conf_base_vol_adaptive_lp_0.yml`, `conf/scripts/conf_quick_eth_usdc_lp_0.yml` | unmapped | Target 有脚本配置文件，但无 baseline 同等“active strategy”统一切换层。 |
| Dashboard API（history/tracking/snapshots/strategy_meta/capital_events） | `web/api.py:79-763` | `N/A` | unmapped | Target仓库未内置该API服务。 |
| Subgraph查询客户端 | `src/subgraph_client.py:49-150` | `N/A` | unmapped | Target仓库未见等价 subgraph 客户端。 |
| 前端静态看板（web/static） | `web/static/*` | `N/A` | unmapped | Phase 1 按规范可外置保留。 |
