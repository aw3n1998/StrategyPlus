"""
WebSocket 实时数据源（仅支持 Bitget）

使用 ccxt.pro 订阅：
  - 多标的 15m OHLCV  → 驱动 Accumulation/Manipulation 检测
  - 多标的  1m OHLCV  → 驱动入场信号检测
  - 多标的 Ticker     → 提供实时价格（trailing stop 使用）

架构：
  - 所有流在独立 asyncio.Task 中持续运行，自动重连
  - 通过 asyncio.Event 通知调用方 K 线收盘事件
  - get_df_15m(symbol) / get_df_1m(symbol) 只返回已收盘的 K 线

修复记录：
  - [M3] 移除 watch_ohlcv 的 limit 参数
  - [L2] 新增 last_15m_recv / last_1m_recv 时间戳
  - [NEW] 多标的支持：每个 symbol 独立维护 DataFrame 和事件
"""
import asyncio
from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import ccxt.pro as ccxtpro
from loguru import logger

from core.detector import PO3Detector


class DataFeed:
    """
    Bitget WebSocket 数据源（多标的版）

    外部使用模式：
        feed = DataFeed(exchange, ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        asyncio.create_task(feed.start())

        await feed.candle_closed_15m["BTC/USDT:USDT"].wait()
        feed.candle_closed_15m["BTC/USDT:USDT"].clear()
        df = feed.get_df_15m("BTC/USDT:USDT")

        price = feed.last_price["BTC/USDT:USDT"]
    """

    _MAX_BARS = 300

    def __init__(self, exchange: ccxtpro.Exchange, symbols: list):
        self.exchange = exchange
        self.symbols = symbols

        # 每个 symbol 独立的 DataFrame 和事件
        self._df_15m: Dict[str, pd.DataFrame] = {s: pd.DataFrame() for s in symbols}
        self._df_1m: Dict[str, pd.DataFrame] = {s: pd.DataFrame() for s in symbols}

        self.last_price: Dict[str, float] = {s: 0.0 for s in symbols}
        self.last_price_ts: Dict[str, Optional[datetime]] = {s: None for s in symbols}

        self.candle_closed_15m: Dict[str, asyncio.Event] = {
            s: asyncio.Event() for s in symbols
        }
        self.candle_closed_1m: Dict[str, asyncio.Event] = {
            s: asyncio.Event() for s in symbols
        }

        self._last_ts_15m: Dict[str, Optional[int]] = {s: None for s in symbols}
        self._last_ts_1m: Dict[str, Optional[int]] = {s: None for s in symbols}

        self.last_15m_recv: Dict[str, datetime] = {s: datetime.now() for s in symbols}
        self.last_1m_recv: Dict[str, datetime] = {s: datetime.now() for s in symbols}
        self.last_ticker_recv: Dict[str, datetime] = {s: datetime.now() for s in symbols}

        self._running: bool = False
        self._tasks: list = []

    async def start(self) -> None:
        """启动全部 WebSocket 流（先初始化历史数据）"""
        self._running = True
        logger.info(f"[WS] DataFeed 启动 | symbols={self.symbols}")

        await self._init_history()

        # 为每个 symbol 启动 3 个流（15m + 1m + ticker）
        self._tasks = []
        for symbol in self.symbols:
            self._tasks.append(
                asyncio.create_task(self._stream_ohlcv(symbol, "15m"), name=f"ws_15m_{symbol}")
            )
            self._tasks.append(
                asyncio.create_task(self._stream_ohlcv(symbol, "1m"), name=f"ws_1m_{symbol}")
            )
            self._tasks.append(
                asyncio.create_task(self._stream_ticker(symbol), name=f"ws_ticker_{symbol}")
            )

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        """停止所有流"""
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        logger.info("[WS] DataFeed 已停止")

    def get_df_15m(self, symbol: str) -> pd.DataFrame:
        """返回已收盘的 15m K 线"""
        df = self._df_15m.get(symbol, pd.DataFrame())
        if len(df) < 2:
            return df
        return df.iloc[:-1].copy()

    def get_df_1m(self, symbol: str) -> pd.DataFrame:
        """返回已收盘的 1m K 线"""
        df = self._df_1m.get(symbol, pd.DataFrame())
        if len(df) < 2:
            return df
        return df.iloc[:-1].copy()

    def is_ready(self, symbol: str) -> bool:
        """指定 symbol 的数据是否已初始化"""
        return (
            len(self._df_15m.get(symbol, [])) >= 20
            and len(self._df_1m.get(symbol, [])) >= 20
        )

    def ws_health(self, symbol: str) -> dict:
        """指定 symbol 的 WS 流健康状态"""
        now = datetime.now()
        return {
            "15m_stale_secs": (now - self.last_15m_recv.get(symbol, now)).total_seconds(),
            "1m_stale_secs": (now - self.last_1m_recv.get(symbol, now)).total_seconds(),
            "ticker_stale_secs": (now - self.last_ticker_recv.get(symbol, now)).total_seconds(),
        }

    async def _init_history(self) -> None:
        """用 REST 初始化历史 K 线"""
        for symbol in self.symbols:
            for timeframe, target in [("15m", "_df_15m"), ("1m", "_df_1m")]:
                for attempt in range(3):
                    try:
                        raw = await self.exchange.fetch_ohlcv(
                            symbol, timeframe, limit=200
                        )
                        if not raw:
                            raise ValueError(f"{symbol} {timeframe} fetch_ohlcv 返回空")
                        df = PO3Detector.candles_to_df(raw)
                        self.__dict__[target][symbol] = df
                        if timeframe == "15m":
                            self._last_ts_15m[symbol] = raw[-1][0]
                        else:
                            self._last_ts_1m[symbol] = raw[-1][0]
                        logger.info(f"[WS] {symbol} {timeframe} 历史初始化: {len(df)} 根")
                        break
                    except Exception as e:
                        logger.warning(
                            f"[WS] {symbol} {timeframe} 初始化失败 ({attempt+1}/3): {e}"
                        )
                        await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"[WS] {symbol} {timeframe} 历史初始化全部失败")

    async def _stream_ohlcv(self, symbol: str, timeframe: str) -> None:
        """持续订阅指定 symbol + 时间框架的 OHLCV"""
        reconnect_delay = 1
        while self._running:
            try:
                ohlcv_list = await self.exchange.watch_ohlcv(symbol, timeframe)
                if not ohlcv_list:
                    continue

                reconnect_delay = 1
                new_df = PO3Detector.candles_to_df(ohlcv_list)

                if len(new_df) > self._MAX_BARS:
                    new_df = new_df.iloc[-self._MAX_BARS:]

                if timeframe == "15m":
                    new_ts = ohlcv_list[-1][0]
                    candle_closed = (
                        self._last_ts_15m[symbol] is not None
                        and new_ts != self._last_ts_15m[symbol]
                    )
                    self._df_15m[symbol] = new_df
                    self._last_ts_15m[symbol] = new_ts
                    self.last_15m_recv[symbol] = datetime.now()
                    if candle_closed:
                        logger.debug(f"[WS] {symbol} 15m K线收盘")
                        self.candle_closed_15m[symbol].set()

                elif timeframe == "1m":
                    new_ts = ohlcv_list[-1][0]
                    candle_closed = (
                        self._last_ts_1m[symbol] is not None
                        and new_ts != self._last_ts_1m[symbol]
                    )
                    self._df_1m[symbol] = new_df
                    self._last_ts_1m[symbol] = new_ts
                    self.last_1m_recv[symbol] = datetime.now()
                    if candle_closed:
                        logger.debug(f"[WS] {symbol} 1m K线收盘")
                        self.candle_closed_1m[symbol].set()

            except asyncio.CancelledError:
                break
            except ccxtpro.NetworkError as e:
                logger.warning(f"[WS] {symbol} {timeframe} 断开: {e}，{reconnect_delay}s 后重连")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
            except Exception as e:
                logger.error(f"[WS] {symbol} {timeframe} 异常: {e}，{reconnect_delay}s 后重连")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _stream_ticker(self, symbol: str) -> None:
        """持续订阅实时价格"""
        reconnect_delay = 1
        while self._running:
            try:
                ticker = await self.exchange.watch_ticker(symbol)
                price = float(ticker.get("last") or ticker.get("close") or 0)
                if price > 0:
                    self.last_price[symbol] = price
                    self.last_price_ts[symbol] = datetime.now()
                    self.last_ticker_recv[symbol] = datetime.now()
                reconnect_delay = 1
            except asyncio.CancelledError:
                break
            except ccxtpro.NetworkError as e:
                logger.warning(f"[WS] {symbol} Ticker 断开: {e}，{reconnect_delay}s 后重连")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
            except Exception as e:
                logger.error(f"[WS] {symbol} Ticker 异常: {e}，{reconnect_delay}s 后重连")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
