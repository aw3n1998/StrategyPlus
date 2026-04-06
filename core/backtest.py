"""
PO3/AMD 回测引擎

支持模式：
    python main.py --backtest --data data/btc_15m.csv --data-1m data/btc_1m.csv
    python main.py --backtest --data data/btc_15m.csv  # 仅 15m 回测

CSV 格式要求（标准 OHLCV）：
    timestamp,open,high,low,close,volume
    2024-01-01 00:00:00,42000,42100,41900,42050,1234.56

回测输出：
    - 总交易次数、胜率、盈亏比
    - 最大回撤、夏普比率
    - 每笔交易明细
    - 权益曲线
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from loguru import logger

from config.settings import load_config, PO3Config
from core.detector import PO3Detector, EntrySignal, ManipulationEvent, AccumulationRange
from core.risk_manager import RiskManager, TradeRecord


@dataclass
class BacktestResult:
    """回测结果汇总"""
    symbol: str
    start_date: str
    end_date: str
    initial_equity: float
    final_equity: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    total_pnl_after_fees: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_holding_time_min: float
    max_consecutive_losses: int
    trades: List[dict] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 65,
            f"  回测结果  |  {self.symbol}",
            "=" * 65,
            f"  区间     : {self.start_date} → {self.end_date}",
            f"  初始权益 : {self.initial_equity:.2f} USDT",
            f"  最终权益 : {self.final_equity:.2f} USDT",
            f"  总收益   : {self.total_pnl:+.2f} USDT ({(self.final_equity/self.initial_equity-1)*100:+.2f}%)",
            f"  净收益   : {self.total_pnl_after_fees:+.2f} USDT (扣费后)",
            f"  交易次数 : {self.total_trades}",
            f"  胜率     : {self.win_rate:.1f}% ({self.wins}胜 {self.losses}负)",
            f"  盈亏比   : {self.profit_factor:.2f}",
            f"  平均盈利 : {self.avg_win:+.2f} USDT",
            f"  平均亏损 : {self.avg_loss:+.2f} USDT",
            f"  最大回撤 : {self.max_drawdown:.2f} USDT ({self.max_drawdown_pct:.2f}%)",
            f"  夏普比率 : {self.sharpe_ratio:.2f}",
            f"  连续最大亏损: {self.max_consecutive_losses}次",
            f"  平均持仓 : {self.avg_holding_time_min:.1f} 分钟",
            "=" * 65,
        ]
        return "\n".join(lines)


class BacktestEngine:
    """
    PO3 回测引擎

    工作流程：
    1. 加载 15m 和 1m 历史 K 线
    2. 逐根 K 线模拟实盘运行
    3. 15m 收盘 → 检测 Accumulation/Manipulation
    4. Manipulation 确认后 → 用 1m 检测入场
    5. 入场后 → 模拟 TP/SL/trailing 逻辑
    6. 输出统计报告
    """

    def __init__(self, cfg: PO3Config, initial_equity: float = 10000.0):
        self.cfg = cfg
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.risk = RiskManager(cfg)
        self.risk.set_daily_start_equity(initial_equity)
        self.detector = PO3Detector(cfg)

        # 回测状态
        self._trades: List[dict] = []
        self._equity_curve: List[dict] = []
        self._current_manip: Optional[ManipulationEvent] = None
        self._in_position = False
        self._position_entry: Optional[dict] = None
        self._peak_equity = initial_equity
        self._max_drawdown = 0.0

    def run(
        self,
        df_15m: pd.DataFrame,
        df_1m: pd.DataFrame,
        symbol: str = "BTC/USDT:USDT",
    ) -> BacktestResult:
        """
        执行回测

        Args:
            df_15m: 15m OHLCV 数据（需包含 open, high, low, close, volume）
            df_1m: 1m OHLCV 数据
            symbol: 交易标的
        """
        logger.info(f"[BACKTEST] 开始回测 {symbol} | "
                     f"15m: {len(df_15m)} 根, 1m: {len(df_1m)} 根")

        # 按 15m K 线逐根推进
        for i in range(20, len(df_15m)):
            df_15m_closed = df_15m.iloc[:i]
            candle_15m = df_15m.iloc[i]

            # 检查持仓是否被 TP/SL 触发
            if self._in_position:
                self._check_position_exit(candle_15m, df_15m_closed)

            # 检测 Accumulation
            acc = self.detector.detect_accumulation(df_15m_closed)
            if acc is None:
                if self._current_manip is not None:
                    self._current_manip = None
                continue

            # 检测 Manipulation
            if self._current_manip is None and not self._in_position:
                manip = self.detector.detect_manipulation(df_15m_closed, acc)
                if manip:
                    self._current_manip = manip
                    self.detector.reset_entry_dedup()
                continue

            # 有 Manipulation 信号，用 1m 找入场点
            if self._current_manip and not self._in_position:
                # 检查 Manipulation 是否过期
                age_bars = self._count_15m_bars_since(
                    df_15m_closed, self._current_manip.timestamp
                )
                if age_bars > self.cfg.manip_max_age_bars:
                    self._current_manip = None
                    continue

                # 找到对应的 1m 窗口
                df_1m_window = self._get_1m_window_for_15m(
                    df_1m, candle_15m, df_15m_closed
                )
                if df_1m_window is not None and len(df_1m_window) >= 5:
                    signal = self.detector.detect_entry_signal(
                        df_1m_window, self._current_manip
                    )
                    if signal:
                        self._execute_entry(signal, candle_15m)

        # 回测结束，强制平掉所有持仓
        if self._in_position and self._position_entry:
            self._force_close("backtest_end")

        return self._build_result(symbol, df_15m)

    def _check_position_exit(self, candle_15m, df_15m_closed) -> None:
        """检查持仓是否触发 TP/SL"""
        if not self._position_entry:
            return

        pos = self._position_entry
        high = float(candle_15m["high"])
        low = float(candle_15m["low"])
        close = float(candle_15m["close"])

        direction = pos["direction"]
        sl = pos["stop_loss"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]
        entry = pos["entry_price"]
        atr = pos["atr"]

        # 检查 SL
        if direction == "long" and low <= sl:
            self._close_position(sl, "sl")
            return
        elif direction == "short" and high >= sl:
            self._close_position(sl, "sl")
            return

        # 检查 TP1
        tp1_hit = False
        if direction == "long" and high >= tp1:
            tp1_hit = True
        elif direction == "short" and low <= tp1:
            tp1_hit = True

        if tp1_hit and not pos.get("tp1_hit"):
            pos["tp1_hit"] = True
            # TP1 平仓 50%
            tp1_pnl = self._calc_pnl(direction, entry, tp1, pos["contracts"] * 0.5)
            pos["realized_pnl"] += tp1_pnl
            pos["contracts"] *= 0.5

        # 检查 TP2 或 trailing stop
        if pos.get("tp1_hit"):
            trail_dist = atr * self.cfg.trailing_atr_mult
            if direction == "long":
                new_trail = close - trail_dist
                pos["trailing_sl"] = max(pos.get("trailing_sl", sl), new_trail)
                if close >= tp2 or low <= pos["trailing_sl"]:
                    exit_price = tp2 if close >= tp2 else pos["trailing_sl"]
                    self._close_position(exit_price, "tp2" if close >= tp2 else "trail")
            else:
                new_trail = close + trail_dist
                pos["trailing_sl"] = min(pos.get("trailing_sl", sl), new_trail)
                if close <= tp2 or high >= pos["trailing_sl"]:
                    exit_price = tp2 if close <= tp2 else pos["trailing_sl"]
                    self._close_position(exit_price, "tp2" if close <= tp2 else "trail")

        # 持仓超时检查
        from datetime import datetime
        holding_secs = (datetime.now() - pos["opened_at"]).total_seconds()
        if holding_secs > self.cfg.max_holding_time_secs:
            self._close_position(close, "timeout")

    def _execute_entry(self, signal: EntrySignal, candle_15m) -> None:
        """模拟入场"""
        entry = signal.entry_price
        atr = signal.manipulation.acc_range.atr
        sl, tp1, tp2 = self.risk.calculate_tp_sl(
            entry, signal.manipulation.extreme, atr, signal.direction
        )
        contracts = self.risk.calculate_position_size(self.equity, entry, sl)
        if contracts <= 0:
            return

        can, _ = self.risk.can_trade(self.equity)
        if not can:
            return

        self._in_position = True
        self._position_entry = {
            "direction": signal.direction,
            "entry_price": entry,
            "stop_loss": sl,
            "tp1": tp1,
            "tp2": tp2,
            "contracts": contracts,
            "atr": atr,
            "opened_at": candle_15m.name if hasattr(candle_15m, 'name') else datetime.now(),
            "tp1_hit": False,
            "trailing_sl": sl,
            "realized_pnl": 0.0,
        }
        self._current_manip = None

    def _close_position(self, exit_price: float, reason: str) -> None:
        """平仓并记录"""
        if not self._position_entry:
            return

        pos = self._position_entry
        pnl = pos["realized_pnl"] + self._calc_pnl(
            pos["direction"], pos["entry_price"], exit_price, pos["contracts"]
        )

        # 扣手续费
        entry_value = pos["entry_price"] * pos["contracts"]
        close_value = exit_price * pos["contracts"]
        fees = (entry_value + close_value) * self.cfg.taker_fee
        pnl_after_fees = pnl - fees

        self.equity += pnl_after_fees
        if self.equity > self._peak_equity:
            self._peak_equity = self.equity

        drawdown = self._peak_equity - self.equity
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown

        self._equity_curve.append({
            "time": str(pos["opened_at"])[:16],
            "equity": round(self.equity, 2),
            "pnl": round(pnl_after_fees, 2),
        })

        holding_secs = (datetime.now() - pos["opened_at"]).total_seconds()
        self._trades.append({
            "direction": pos["direction"],
            "entry": pos["entry_price"],
            "exit": exit_price,
            "contracts": pos["contracts"],
            "pnl": round(pnl, 4),
            "pnl_after_fees": round(pnl_after_fees, 4),
            "reason": reason,
            "holding_min": round(holding_secs / 60, 1),
            "tp1_hit": pos.get("tp1_hit", False),
        })

        self._in_position = False
        self._position_entry = None

    def _force_close(self, reason: str) -> None:
        if self._position_entry:
            self._close_position(
                self._position_entry["entry_price"], reason
            )

    def _calc_pnl(self, direction: str, entry: float, exit: float, contracts: float) -> float:
        if direction == "long":
            return (exit - entry) * contracts
        return (entry - exit) * contracts

    def _count_15m_bars_since(self, df: pd.DataFrame, ts: datetime) -> int:
        """计算从某个时间戳到现在经过了多少根 15m K 线"""
        count = 0
        for idx in df.index:
            if idx > ts:
                count += 1
        return count

    def _get_1m_window_for_15m(
        self, df_1m: pd.DataFrame, candle_15m, df_15m_closed: pd.DataFrame
    ) -> Optional[pd.DataFrame]:
        """获取与当前 15m K 线对应的 1m 窗口"""
        if len(df_1m) < 20:
            return None
        # 返回最近 20 根 1m K 线
        return df_1m.iloc[-20:]

    def _build_result(self, symbol: str, df_15m: pd.DataFrame) -> BacktestResult:
        """构建回测结果"""
        total_trades = len(self._trades)
        wins = sum(1 for t in self._trades if t["pnl"] > 0)
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        total_pnl = sum(t["pnl"] for t in self._trades)
        total_pnl_after_fees = sum(t["pnl_after_fees"] for t in self._trades)

        win_trades = [t for t in self._trades if t["pnl"] > 0]
        loss_trades = [t for t in self._trades if t["pnl"] <= 0]
        avg_win = sum(t["pnl"] for t in win_trades) / len(win_trades) if win_trades else 0
        avg_loss = sum(t["pnl"] for t in loss_trades) / len(loss_trades) if loss_trades else 0

        gross_profit = sum(t["pnl"] for t in win_trades)
        gross_loss = abs(sum(t["pnl"] for t in loss_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # 最大连续亏损
        max_consec = 0
        curr_consec = 0
        for t in self._trades:
            if t["pnl"] <= 0:
                curr_consec += 1
                max_consec = max(max_consec, curr_consec)
            else:
                curr_consec = 0

        # 夏普比率（简化版）
        if self._trades:
            pnl_list = [t["pnl_after_fees"] for t in self._trades]
            avg_ret = sum(pnl_list) / len(pnl_list)
            std_ret = pd.Series(pnl_list).std()
            sharpe = (avg_ret / std_ret * (252 * 96) ** 0.5) if std_ret > 0 else 0
        else:
            sharpe = 0

        avg_holding = (
            sum(t["holding_min"] for t in self._trades) / total_trades
            if total_trades > 0 else 0
        )

        start_date = str(df_15m.index[0])[:16] if len(df_15m) > 0 else "N/A"
        end_date = str(df_15m.index[-1])[:16] if len(df_15m) > 0 else "N/A"

        return BacktestResult(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_equity=self.initial_equity,
            final_equity=self.equity,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_after_fees=total_pnl_after_fees,
            max_drawdown=self._max_drawdown,
            max_drawdown_pct=(self._max_drawdown / self._peak_equity * 100) if self._peak_equity > 0 else 0,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_holding_time_min=avg_holding,
            max_consecutive_losses=max_consec,
            trades=self._trades,
            equity_curve=self._equity_curve,
        )


def load_csv_ohlcv(path: str) -> pd.DataFrame:
    """
    加载 CSV OHLCV 数据
    支持格式：
    - timestamp,open,high,low,close,volume
    - 时间戳可以是 Unix ms 或 ISO 格式
    """
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        # 尝试解析 Unix 毫秒时间戳
        if df["timestamp"].iloc[0] > 1e12:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    elif df.index.name != "timestamp":
        df.index = pd.to_datetime(df.index)

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    df = df.sort_index()
    return df


async def run_backtest(cfg: PO3Config, data_path: str, data_1m_path: Optional[str] = None, initial_equity: float = 10000.0) -> None:
    """
    运行回测
    """
    print(f"\n{'='*65}")
    print(f"  PO3/AMD 回测引擎")
    print(f"{'='*65}")
    print(f"  数据文件 : {data_path}")
    if data_1m_path:
        print(f"  1m 数据  : {data_1m_path}")
    print(f"  初始权益 : {initial_equity:.0f} USDT")
    print(f"  杠杆     : {cfg.leverage}x")
    print(f"  手续费   : Maker={cfg.maker_fee*100:.2f}% Taker={cfg.taker_fee*100:.2f}%")
    print(f"{'='*65}\n")

    engine = BacktestEngine(cfg, initial_equity=initial_equity)

    try:
        df_15m = load_csv_ohlcv(data_path)
    except Exception as e:
        print(f"[ERROR] 加载 15m 数据失败: {e}")
        return

    df_1m = None
    if data_1m_path:
        try:
            df_1m = load_csv_ohlcv(data_1m_path)
        except Exception as e:
            print(f"[WARNING] 加载 1m 数据失败: {e}，将使用简化模式")

    if df_1m is None:
        # 没有 1m 数据，用 15m 模拟
        print("[WARNING] 无 1m 数据，使用简化回测模式（精度较低）")
        df_1m = df_15m

    result = engine.run(df_15m, df_1m, symbol=cfg.symbol)

    # 打印结果
    print(result.summary())

    # 保存详细结果
    output_path = Path("data") / f"backtest_{datetime.now():%Y%m%d_%H%M%S}.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "symbol": result.symbol,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "initial_equity": result.initial_equity,
                "final_equity": result.final_equity,
                "total_trades": result.total_trades,
                "wins": result.wins,
                "losses": result.losses,
                "win_rate": result.win_rate,
                "total_pnl": result.total_pnl,
                "total_pnl_after_fees": result.total_pnl_after_fees,
                "max_drawdown": result.max_drawdown,
                "max_drawdown_pct": result.max_drawdown_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "profit_factor": result.profit_factor,
                "avg_win": result.avg_win,
                "avg_loss": result.avg_loss,
                "avg_holding_time_min": result.avg_holding_time_min,
                "max_consecutive_losses": result.max_consecutive_losses,
            },
            "trades": result.trades,
            "equity_curve": result.equity_curve,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  详细结果已保存: {output_path}")
    print()
