import json
import math
import statistics
import urllib.parse
import urllib.request


def get_realized_vol_7d(symbol: str = "ETHUSDT", interval: str = "1h", timeout: int = 8) -> float | None:
    """Return 7-day annualized realized volatility in percent using Binance public klines."""
    lookback_points = 24 * 7 + 1
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": lookback_points})
    url = f"https://api.binance.com/api/v3/klines?{query}"

    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, list) or len(payload) < 3:
        return None

    closes = []
    for row in payload:
        try:
            closes.append(float(row[4]))
        except Exception:
            continue

    if len(closes) < 3:
        return None

    log_returns = []
    for prev, curr in zip(closes[:-1], closes[1:]):
        if prev <= 0 or curr <= 0:
            continue
        log_returns.append(math.log(curr / prev))

    if len(log_returns) < 2:
        return None

    sigma_period = statistics.stdev(log_returns)
    periods_per_year = 24 * 365
    sigma_annual = sigma_period * math.sqrt(periods_per_year)
    return sigma_annual * 100
