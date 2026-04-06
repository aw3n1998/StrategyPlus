"""
波动率过滤器

用于判断当前市场是否处于极端波动状态，避免在暴跌/暴涨行情中
执行 PO3 策略（此时累积区间识别容易失效）。

使用方式：
    filter = VolatilityFilter(exchange, cfg)
    is_safe = await filter.check(symbol)
"""
from typing import Optional

import ccxt.pro as ccxtpro
from loguru import logger

from core.detector import PO3Detector


class VolatilityFilter:
    """
    基于日线 ATR 百分比判断市场波动率。

    逻辑：
    1. 获取最近 N 天日线数据
    2. 计算 ATR(lookback_days)
    3. ATR% = ATR / 当前价格
    4. 若 ATR% > threshold，则判定为极端波动，暂停交易
    """

    def __init__(self, exchange: ccxtpro.Exchange, config):
        self.exchange = exchange
        self.cfg = config
        self._last_check_result: dict = {}  # symbol → (is_safe, atr_pct, timestamp)
        self._check_interval_secs = 300  # 每 5 分钟检查一次

    async def check(self, symbol: str) -> bool:
        """
        检查指定标的波动率是否在可接受范围内。
        返回 True = 安全可交易，False = 波动过大应暂停。
        """
        if not self.cfg.volatility_filter_enabled:
            return True

        # 缓存检查（避免频繁调用 REST）
        import time
        cached = self._last_check_result.get(symbol)
        if cached:
            is_safe, atr_pct, ts = cached
            if time.time() - ts < self._check_interval_secs:
                return is_safe

        try:
            is_safe, atr_pct = await self._calculate_volatility(symbol)
            self._last_check_result[symbol] = (is_safe, atr_pct, time.time())

            if not is_safe:
                logger.warning(
                    f"[VOL] ⚠ {symbol} 波动率过高: {atr_pct*100:.2f}% > "
                    f"{self.cfg.volatility_atr_daily_threshold*100:.1f}%，暂停交易"
                )
            else:
                logger.debug(f"[VOL] {symbol} 波动率正常: {atr_pct*100:.2f}%")

            return is_safe

        except Exception as e:
            logger.warning(f"[VOL] 波动率检查失败: {e}，默认允许交易")
            return True

    async def _calculate_volatility(self, symbol: str) -> tuple:
        """
        计算日线 ATR 百分比。
        返回 (is_safe, atr_pct)
        模拟模式直接返回安全状态
        """
        # 模拟模式：直接返回安全状态
        if self.cfg.api_key == "":
            return True, 0.0
        
        lookback = self.cfg.volatility_lookback_days
        # 需要足够数据计算 ATR
        raw = await self.exchange.fetch_ohlcv(
            symbol, "1d", limit=lookback + 20
        )
        if not raw or len(raw) < lookback + 5:
            logger.warning(f"[VOL] {symbol} 日线数据不足，跳过波动率检查")
            return True, 0.0

        df = PO3Detector.candles_to_df(raw)
        atr = PO3Detector.get_current_atr(df, length=lookback)
        current_price = float(df["close"].iloc[-1])

        if current_price <= 0 or atr <= 0:
            return True, 0.0

        atr_pct = atr / current_price
        is_safe = atr_pct <= self.cfg.volatility_atr_daily_threshold

        return is_safe, atr_pct

    def get_status(self) -> dict:
        """返回所有已检查标的的波动率状态（供 API 使用）"""
        result = {}
        for symbol, (is_safe, atr_pct, ts) in self._last_check_result.items():
            result[symbol] = {
                "is_safe": is_safe,
                "atr_pct": round(atr_pct * 100, 2),
                "threshold_pct": round(self.cfg.volatility_atr_daily_threshold * 100, 2),
                "checked_at": ts,
            }
        return result
