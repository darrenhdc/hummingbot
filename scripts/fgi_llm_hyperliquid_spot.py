import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Tuple

import pandas as pd

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.utils import split_hb_trading_pair
from hummingbot.core.data_type.common import OrderType
from hummingbot.core.event.events import OrderFilledEvent, TradeType
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


def _load_local_env() -> None:
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        # Environment loading should never crash strategy startup.
        pass


_load_local_env()


class FgiLlmHyperliquidSpot(ScriptStrategyBase):
    # Basic market config
    connector_name: str = os.getenv("STRAT_CONNECTOR", "hyperliquid")
    trading_pair: str = os.getenv("STRAT_TRADING_PAIR", "BTC-USDC")
    markets = {connector_name: {trading_pair}}

    # Timeframe + trend params
    candle_interval: str = os.getenv("STRAT_CANDLE_INTERVAL", "1h")
    sma_fast: int = int(os.getenv("STRAT_SMA_FAST", "20"))
    sma_slow: int = int(os.getenv("STRAT_SMA_SLOW", "50"))

    # User-confirmed risk defaults
    total_capital_quote: Decimal = Decimal(os.getenv("STRAT_TOTAL_CAPITAL", "20"))
    max_total_exposure_quote: Decimal = Decimal(os.getenv("STRAT_MAX_EXPOSURE_QUOTE", "8"))
    order_size_quote: Decimal = Decimal(os.getenv("STRAT_ORDER_SIZE_QUOTE", "2"))
    max_daily_loss_quote: Decimal = Decimal(os.getenv("STRAT_MAX_DAILY_LOSS_QUOTE", "2"))
    max_daily_trades: int = int(os.getenv("STRAT_MAX_DAILY_TRADES", "3"))
    cooldown_sec: int = int(os.getenv("STRAT_COOLDOWN_SEC", "1800"))

    # FGI gate
    fgi_extreme_fear: int = int(os.getenv("STRAT_FGI_EXTREME_FEAR", "25"))
    fgi_extreme_greed: int = int(os.getenv("STRAT_FGI_EXTREME_GREED", "75"))
    fgi_sma_len: int = int(os.getenv("STRAT_FGI_SMA_LEN", "7"))

    # Execution + exits
    buy_price_offset_pct: Decimal = Decimal(os.getenv("STRAT_BUY_OFFSET_PCT", "0.001"))
    sell_price_offset_pct: Decimal = Decimal(os.getenv("STRAT_SELL_OFFSET_PCT", "0.001"))
    stop_loss_pct: Decimal = Decimal(os.getenv("STRAT_STOP_LOSS_PCT", "0.05"))
    take_profit_pct: Decimal = Decimal(os.getenv("STRAT_TAKE_PROFIT_PCT", "0.03"))
    min_position_quote: Decimal = Decimal(os.getenv("STRAT_MIN_POSITION_QUOTE", "1"))

    # LLM params
    llm_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    llm_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    llm_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    llm_timeout_sec: int = int(os.getenv("DEEPSEEK_TIMEOUT_SEC", "5"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_min_confidence: float = float(os.getenv("LLM_MIN_CONFIDENCE", "0.70"))
    llm_failsafe_action: str = os.getenv("LLM_FAILSAFE_ACTION", "hold").lower()
    llm_api_style: str = os.getenv("DEEPSEEK_API_STYLE", "auto").lower()  # auto/openai/anthropic

    # Runtime control
    decision_interval_sec: int = int(os.getenv("STRAT_DECISION_INTERVAL_SEC", "30"))
    fgi_refresh_sec: int = int(os.getenv("STRAT_FGI_REFRESH_SEC", "3600"))

    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)

        self.base_asset, self.quote_asset = split_hb_trading_pair(self.trading_pair)
        self.candles = CandlesFactory.get_candle(CandlesConfig(
            connector=self.connector_name,
            trading_pair=self.trading_pair,
            interval=self.candle_interval,
            max_records=max(self.sma_slow + 20, 120),
        ))
        self.candles.start()

        # FSM/runtime states
        self.state: str = "IDLE"
        self.last_state_reason: str = "startup"
        self.last_decision_ts: float = 0
        self.last_trade_ts: float = 0
        self.last_candle_ts: Optional[int] = None

        # Daily controls
        self.current_day: Optional[str] = None
        self.daily_start_equity_quote: Optional[Decimal] = None
        self.daily_trade_count: int = 0

        # FGI cache
        self.fgi_last_fetch_ts: float = 0
        self.fgi_series_cache: Optional[list] = None

        # Position proxy
        self.entry_price_estimate: Optional[Decimal] = None
        self.last_llm_decision: Dict = {"action": "hold", "confidence": 0.0, "size_ratio": 0.0, "reason": "init"}
        self.last_signal_snapshot: Dict = {}

    async def on_stop(self):
        self.candles.stop()

    def on_tick(self):
        if not self.ready_to_trade:
            return
        if not self.candles.ready:
            self._set_state("CHECK_DATA", "candles_not_ready")
            return
        now = self.current_timestamp
        if now - self.last_decision_ts < self.decision_interval_sec:
            return
        self.last_decision_ts = now

        self._roll_daily_window_if_needed()
        self._set_state("CHECK_DATA", "tick")

        if not self._market_data_ready():
            self._hold("market_data_unavailable")
            return

        # Only evaluate on new candle to reduce noise and duplicate decisions.
        candle_ts = int(self.candles.candles_df["timestamp"].iloc[-1])
        if self.last_candle_ts == candle_ts:
            return
        self.last_candle_ts = candle_ts

        # Avoid stacking multiple open orders.
        if self._has_active_orders():
            self._hold("active_order_exists")
            return

        if not self._passes_hard_risk_limits():
            self._hold("hard_risk_rejected")
            return

        fgi_lag, fgi_sma = self._get_fgi_lag_and_sma()
        trend_bull = self._is_trend_bullish()
        mid_price = self._mid_price()
        if mid_price is None:
            self._hold("mid_price_unavailable")
            return

        exposure_quote = self._base_balance_total() * mid_price
        in_position = exposure_quote >= self.min_position_quote

        self.last_signal_snapshot = {
            "fgi_lag": fgi_lag,
            "fgi_sma": fgi_sma,
            "trend_bull": trend_bull,
            "exposure_quote": float(exposure_quote),
        }

        if in_position:
            self._manage_position(fgi_lag=fgi_lag, trend_bull=trend_bull, mid_price=mid_price, exposure_quote=exposure_quote)
            return

        self._set_state("CHECK_FGI_GATE", "flat_position")
        if fgi_lag is None:
            self._hold("fgi_unavailable")
            return
        if fgi_lag < self.fgi_extreme_fear:
            self._hold("fgi_extreme_fear_no_new_long")
            return
        if fgi_lag > self.fgi_extreme_greed:
            self._hold("fgi_extreme_greed_no_new_long")
            return
        if not trend_bull:
            self._hold("trend_not_bullish")
            return

        self._set_state("CHECK_LLM", "long_candidate")
        llm_decision = self._get_llm_decision(
            fgi_lag=fgi_lag,
            fgi_sma=fgi_sma,
            trend_bull=trend_bull,
            in_position=False,
            exposure_quote=exposure_quote,
        )
        self.last_llm_decision = llm_decision
        if llm_decision["action"] != "buy":
            self._hold("llm_not_buy")
            return
        if llm_decision["confidence"] < self.llm_min_confidence:
            self._hold("llm_confidence_too_low")
            return

        remaining_quota = self.max_total_exposure_quote - exposure_quote
        if remaining_quota <= Decimal("0"):
            self._hold("max_exposure_reached")
            return
        size_ratio = Decimal(str(max(0.0, min(1.0, llm_decision.get("size_ratio", 1.0)))))
        order_budget_quote = min(self.order_size_quote * size_ratio, remaining_quota)
        if order_budget_quote <= Decimal("0"):
            self._hold("order_budget_zero")
            return

        self._set_state("READY_TO_BUY", f"budget={order_budget_quote}")
        self._place_limit_buy(mid_price=mid_price, order_budget_quote=order_budget_quote)

    def did_fill_order(self, event: OrderFilledEvent):
        if event.trading_pair != self.trading_pair:
            return
        if event.trade_type == TradeType.BUY:
            self.entry_price_estimate = Decimal(str(event.price))
        self.log_with_clock(
            logging.INFO,
            f"Fill: {event.trade_type.name} {event.amount} {self.base_asset} @ {event.price}",
        )

    def format_status(self) -> str:
        if not self.ready_to_trade:
            return "Market connectors are not ready."

        lines = [f"State: {self.state} | Reason: {self.last_state_reason}"]
        lines.append(f"Pair: {self.trading_pair} | Interval: {self.candle_interval}")
        lines.append(
            f"Daily: trades={self.daily_trade_count}/{self.max_daily_trades} "
            f"cooldown_sec={self.cooldown_sec}"
        )
        lines.append(
            f"Exposure cap: {self.max_total_exposure_quote} {self.quote_asset} | "
            f"Order size: {self.order_size_quote} {self.quote_asset}"
        )
        lines.append(f"FGI gate: <{self.fgi_extreme_fear}=block long, >{self.fgi_extreme_greed}=reduce/no new long")
        lines.append(
            f"LLM: model={self.llm_model} conf>={self.llm_min_confidence} "
            f"temp={self.llm_temperature}"
        )
        lines.append(f"Last signal: {self.last_signal_snapshot}")
        lines.append(f"Last LLM: {self.last_llm_decision}")
        return "\n".join(lines)

    # -------------------- FSM helpers --------------------
    def _set_state(self, state: str, reason: str):
        self.state = state
        self.last_state_reason = reason

    def _hold(self, reason: str):
        self._set_state("HOLD", reason)

    # -------------------- Risk + balances --------------------
    def _market_data_ready(self) -> bool:
        try:
            _ = self.connectors[self.connector_name].get_mid_price(self.trading_pair)
            return True
        except Exception:
            return False

    def _mid_price(self) -> Optional[Decimal]:
        try:
            return Decimal(str(self.connectors[self.connector_name].get_mid_price(self.trading_pair)))
        except Exception:
            return None

    def _base_balance_total(self) -> Decimal:
        return Decimal(str(self.connectors[self.connector_name].get_balance(self.base_asset)))

    def _quote_balance_available(self) -> Decimal:
        return Decimal(str(self.connectors[self.connector_name].get_available_balance(self.quote_asset)))

    def _has_active_orders(self) -> bool:
        pair_orders = [o for o in self.get_active_orders(self.connector_name) if o.trading_pair == self.trading_pair]
        return len(pair_orders) > 0

    def _roll_daily_window_if_needed(self):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mid = self._mid_price()
        if mid is None:
            return
        equity = self._current_equity_quote(mid)
        if self.current_day != day:
            self.current_day = day
            self.daily_trade_count = 0
            self.daily_start_equity_quote = equity

    def _current_equity_quote(self, mid_price: Decimal) -> Decimal:
        base = self._base_balance_total()
        quote = Decimal(str(self.connectors[self.connector_name].get_balance(self.quote_asset)))
        return quote + base * mid_price

    def _passes_hard_risk_limits(self) -> bool:
        self._set_state("CHECK_RISK", "evaluate_limits")
        now = self.current_timestamp
        if self.last_trade_ts and now - self.last_trade_ts < self.cooldown_sec:
            return False
        if self.daily_trade_count >= self.max_daily_trades:
            return False

        mid = self._mid_price()
        if mid is None:
            return False
        equity = self._current_equity_quote(mid)
        if self.daily_start_equity_quote is not None:
            drawdown = self.daily_start_equity_quote - equity
            if drawdown >= self.max_daily_loss_quote:
                return False
        exposure_quote = self._base_balance_total() * mid
        if exposure_quote > self.max_total_exposure_quote:
            return False
        return True

    # -------------------- Signals --------------------
    def _is_trend_bullish(self) -> bool:
        self._set_state("CHECK_TREND", "compute_sma")
        df = self.candles.candles_df
        if df is None or len(df) < self.sma_slow:
            return False
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(closes) < self.sma_slow:
            return False
        fast = float(closes.tail(self.sma_fast).mean())
        slow = float(closes.tail(self.sma_slow).mean())
        return fast > slow

    def _fetch_fgi_series(self) -> Optional[list]:
        now = self.current_timestamp
        if self.fgi_series_cache is not None and now - self.fgi_last_fetch_ts < self.fgi_refresh_sec:
            return self.fgi_series_cache
        url = "https://api.alternative.me/fng/?limit=30&format=json"
        try:
            req = urllib.request.Request(url=url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            rows = raw.get("data", [])
            parsed = []
            for r in rows:
                val = int(r["value"])
                ts = int(r["timestamp"])
                parsed.append((ts, val))
            parsed.sort(key=lambda x: x[0])  # oldest -> newest
            self.fgi_series_cache = parsed
            self.fgi_last_fetch_ts = now
            return parsed
        except Exception:
            return self.fgi_series_cache

    def _get_fgi_lag_and_sma(self) -> Tuple[Optional[int], Optional[float]]:
        self._set_state("CHECK_FGI_GATE", "fetch_fgi")
        series = self._fetch_fgi_series()
        if not series or len(series) == 0:
            return None, None
        values = [v for _, v in series]
        if len(values) >= 2:
            lag = values[-2]  # use t-1 to avoid lookahead
            lag_series = values[:-1]
        else:
            lag = values[-1]
            lag_series = values
        window = lag_series[-self.fgi_sma_len:] if len(lag_series) >= 1 else [lag]
        sma = sum(window) / len(window)
        return lag, sma

    # -------------------- LLM --------------------
    def _llm_prompt(self, fgi_lag: Optional[int], fgi_sma: Optional[float], trend_bull: bool, in_position: bool, exposure_quote: Decimal) -> str:
        return (
            f"You are a conservative crypto execution filter for {self.trading_pair} spot.\n"
            "Return strict JSON only with keys: action, confidence, size_ratio, reason.\n"
            "Rules:\n"
            "- action in [buy, sell, hold]\n"
            "- confidence in [0,1]\n"
            "- size_ratio in [0,1]\n"
            "- If uncertain, choose hold.\n\n"
            "Context:\n"
            f"- pair: {self.trading_pair}\n"
            f"- fgi_lag: {fgi_lag}\n"
            f"- fgi_sma: {fgi_sma}\n"
            f"- trend_bull: {trend_bull}\n"
            f"- in_position: {in_position}\n"
            f"- exposure_quote: {float(exposure_quote)}\n"
            f"- max_exposure_quote: {float(self.max_total_exposure_quote)}\n"
            f"- risk_mode: strict\n"
        )

    def _call_llm_openai_style(self, prompt: str) -> str:
        base = self.llm_base_url.rstrip("/")
        url = f"{base}/chat/completions"
        payload = {
            "model": self.llm_model,
            "temperature": self.llm_temperature,
            "messages": [
                {"role": "system", "content": "You are a strict JSON-only trading decision engine."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.llm_api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.llm_timeout_sec) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    def _call_llm_anthropic_style(self, prompt: str) -> str:
        base = self.llm_base_url.rstrip("/")
        url = f"{base}/v1/messages"
        payload = {
            "model": self.llm_model,
            "max_tokens": 256,
            "temperature": self.llm_temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "x-api-key": self.llm_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.llm_timeout_sec) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result.get("content", [])
        if not content:
            return '{"action":"hold","confidence":0,"size_ratio":0,"reason":"empty_content"}'
        return content[0].get("text", "")

    @staticmethod
    def _extract_json_text(text: str) -> Optional[dict]:
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    def _get_llm_decision(self, fgi_lag: Optional[int], fgi_sma: Optional[float], trend_bull: bool, in_position: bool, exposure_quote: Decimal) -> Dict:
        default_hold = {"action": "hold", "confidence": 0.0, "size_ratio": 0.0, "reason": "llm_default_hold"}
        if not self.llm_api_key:
            default_hold["reason"] = "llm_key_missing"
            return default_hold

        prompt = self._llm_prompt(
            fgi_lag=fgi_lag,
            fgi_sma=fgi_sma,
            trend_bull=trend_bull,
            in_position=in_position,
            exposure_quote=exposure_quote,
        )
        try:
            style = self.llm_api_style
            if style == "auto":
                style = "anthropic" if self.llm_base_url.rstrip("/").endswith("/anthropic") else "openai"
            raw_text = (
                self._call_llm_anthropic_style(prompt)
                if style == "anthropic"
                else self._call_llm_openai_style(prompt)
            )
            parsed = self._extract_json_text(raw_text)
            if not parsed:
                return {"action": self.llm_failsafe_action, "confidence": 0.0, "size_ratio": 0.0, "reason": "llm_parse_failed"}

            action = str(parsed.get("action", "hold")).lower()
            if action not in {"buy", "sell", "hold"}:
                action = "hold"
            confidence = float(parsed.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            size_ratio = float(parsed.get("size_ratio", 0.0))
            size_ratio = max(0.0, min(1.0, size_ratio))
            reason = str(parsed.get("reason", "n/a"))
            return {"action": action, "confidence": confidence, "size_ratio": size_ratio, "reason": reason}
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            return {"action": self.llm_failsafe_action, "confidence": 0.0, "size_ratio": 0.0, "reason": "llm_call_failed"}
        except Exception:
            return {"action": self.llm_failsafe_action, "confidence": 0.0, "size_ratio": 0.0, "reason": "llm_unknown_error"}

    # -------------------- Execution --------------------
    def _place_limit_buy(self, mid_price: Decimal, order_budget_quote: Decimal):
        self._set_state("PLACE_LIMIT_ORDER", "buy")
        price = mid_price * (Decimal("1") - self.buy_price_offset_pct)
        connector = self.connectors[self.connector_name]
        amount = order_budget_quote / price
        amount = connector.quantize_order_amount(self.trading_pair, amount)
        price = connector.quantize_order_price(self.trading_pair, price)
        if amount <= Decimal("0"):
            self._hold("quantized_buy_amount_zero")
            return
        needed_quote = amount * price
        if self._quote_balance_available() < needed_quote:
            self._hold("insufficient_quote_balance")
            return
        self.buy(
            connector_name=self.connector_name,
            trading_pair=self.trading_pair,
            amount=amount,
            order_type=OrderType.LIMIT,
            price=price,
        )
        self.daily_trade_count += 1
        self.last_trade_ts = self.current_timestamp
        self._set_state("COOLDOWN", "buy_submitted")
        self.log_with_clock(logging.INFO, f"BUY LIMIT submitted: amount={amount} price={price}")

    def _place_limit_sell(self, mid_price: Decimal, base_amount: Decimal, reason: str):
        self._set_state("PLACE_LIMIT_ORDER", f"sell:{reason}")
        connector = self.connectors[self.connector_name]
        price = mid_price * (Decimal("1") + self.sell_price_offset_pct)
        amount = connector.quantize_order_amount(self.trading_pair, base_amount)
        price = connector.quantize_order_price(self.trading_pair, price)
        if amount <= Decimal("0"):
            self._hold("quantized_sell_amount_zero")
            return
        self.sell(
            connector_name=self.connector_name,
            trading_pair=self.trading_pair,
            amount=amount,
            order_type=OrderType.LIMIT,
            price=price,
        )
        self.daily_trade_count += 1
        self.last_trade_ts = self.current_timestamp
        self._set_state("COOLDOWN", f"sell_submitted:{reason}")
        self.log_with_clock(logging.INFO, f"SELL LIMIT submitted: amount={amount} price={price} reason={reason}")

    def _manage_position(self, fgi_lag: Optional[int], trend_bull: bool, mid_price: Decimal, exposure_quote: Decimal):
        self._set_state("IN_POSITION", "manage")
        llm_decision = self._get_llm_decision(
            fgi_lag=fgi_lag,
            fgi_sma=self.last_signal_snapshot.get("fgi_sma"),
            trend_bull=trend_bull,
            in_position=True,
            exposure_quote=exposure_quote,
        )
        self.last_llm_decision = llm_decision

        base_total = self._base_balance_total()
        if base_total <= Decimal("0"):
            self._hold("position_balance_zero")
            return

        # 1) Hard stop-loss: full exit if price drops from entry estimate.
        if self.entry_price_estimate is not None and self.entry_price_estimate > Decimal("0"):
            pnl_pct = (mid_price - self.entry_price_estimate) / self.entry_price_estimate
            if pnl_pct <= -self.stop_loss_pct:
                self._place_limit_sell(mid_price=mid_price, base_amount=base_total, reason="stop_loss_full_exit")
                return
            if pnl_pct >= self.take_profit_pct and llm_decision["action"] == "sell" and llm_decision["confidence"] >= self.llm_min_confidence:
                self._place_limit_sell(mid_price=mid_price, base_amount=base_total * Decimal("0.25"), reason="take_profit_partial")
                return

        # 2) Risk reduction when sentiment is too greedy.
        if fgi_lag is not None and fgi_lag > self.fgi_extreme_greed:
            self._place_limit_sell(mid_price=mid_price, base_amount=base_total * Decimal("0.5"), reason="fgi_greed_reduce")
            return

        # 3) LLM high-confidence sell -> reduce 50%.
        if llm_decision["action"] == "sell" and llm_decision["confidence"] >= self.llm_min_confidence:
            self._place_limit_sell(mid_price=mid_price, base_amount=base_total * Decimal("0.5"), reason="llm_reduce")
            return

        self._hold("position_hold")
