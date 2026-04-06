"""
风险管理模块

修复记录：
  - [BUG5]  calculate_position_size 增加杠杆上限约束
  - [BUG10] 权益获取失败时不再使用默认值，返回 None 拒绝开仓
  - [H3]    record_trade_open 存储 TradeRecord；record_trade_close 接收 trade_id
            并更新对应记录，支持历史查询与统计
  - [NEW]   手续费/滑点纳入仓位计算和 PnL 统计
  - [NEW]   连续亏损熔断机制
  - [NEW]   最大持仓时间限制
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class TradeRecord:
    """单笔交易记录"""
    trade_id: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    contracts: float
    risk_usdt: float
    equity_at_entry: float
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    pnl: float = 0.0
    pnl_after_fees: float = 0.0
    status: str = "open"    # "open" | "closed" | "sl" | "timeout"
    fees_paid: float = 0.0
    slippage_cost: float = 0.0


class RiskManager:
    """
    复利风险管理器

    每次入场前：
    1. 检查每日交易次数和亏损上限
    2. 检查连续亏损熔断
    3. 计算本次仓位大小（动态根据当前权益，含手续费/滑点）
       - [BUG5] 强制不超过 leverage × equity 的名义价值上限
    4. 计算 TP1/TP2/SL 价位

    [H3] 记录所有交易：
    - _open_records : {trade_id: TradeRecord}  持仓中的记录
    - _closed_records: [TradeRecord]           历史已平仓记录
    """

    def __init__(self, config, strategy_id: str = "po3"):
        self.cfg = config
        self.strategy_id = strategy_id
        self._today: date = date.today()
        self._daily_trades: int = 0
        self._daily_start_equity: float = 0.0
        self._trade_counter: int = 0

        # [NEW] 连续亏损追踪
        self._consecutive_losses: int = 0
        self._consecutive_loss_cooldown_until: Optional[datetime] = None

        # [H3] 交易记录存储
        self._open_records: Dict[str, TradeRecord] = {}
        self._closed_records: List[TradeRecord] = []

    # ──────────────── 每日重置 ────────────────

    def set_daily_start_equity(self, equity: float) -> None:
        """每日开始时记录起始权益（也用于日内重置判断）"""
        if self._daily_start_equity <= 0:
            self._daily_start_equity = equity
        self._reset_if_new_day(equity)

    def _reset_if_new_day(self, equity: float) -> None:
        today = date.today()
        if today != self._today:
            logger.info(
                f"[RISK-{self.strategy_id}] 新交易日 {today} | "
                f"昨日交易: {self._daily_trades} 次 | "
                f"连续亏损重置: {self._consecutive_losses} → 0 | "
                f"起始权益: {equity:.2f} USDT"
            )
            self._today = today
            self._daily_trades = 0
            self._daily_start_equity = equity
            # 新交易日重置连续亏损计数
            self._consecutive_losses = 0
            self._consecutive_loss_cooldown_until = None

    # ──────────────── 交易许可检查 ────────────────

    def can_trade(self, current_equity: Optional[float]) -> Tuple[bool, str]:
        """
        [BUG10 修复] current_equity 为 None 时直接拒绝（不使用默认值）。
        [NEW] 增加连续亏损熔断检查。
        返回 (是否可以交易, 原因说明)
        """
        if current_equity is None:
            return False, "账户权益获取失败，拒绝开仓"

        self._reset_if_new_day(current_equity)

        if self._daily_start_equity <= 0:
            self._daily_start_equity = current_equity

        # 每日交易次数上限
        if self._daily_trades >= self.cfg.max_daily_trades:
            msg = (
                f"已达每日交易上限 {self.cfg.max_daily_trades} 次 "
                f"(今日: {self._daily_trades})"
            )
            logger.warning(f"[RISK] {msg}")
            return False, msg

        # 每日亏损上限
        daily_loss_pct = self.daily_loss_pct(current_equity)
        if daily_loss_pct >= self.cfg.max_daily_loss:
            msg = (
                f"已达每日亏损上限 "
                f"{daily_loss_pct*100:.1f}% >= {self.cfg.max_daily_loss*100:.1f}%"
            )
            logger.warning(f"[RISK] {msg}")
            return False, msg

        # [NEW] 连续亏损熔断检查
        if self._consecutive_losses >= self.cfg.max_consecutive_losses:
            if self._consecutive_loss_cooldown_until is None:
                self._consecutive_loss_cooldown_until = datetime.now()
                from datetime import timedelta
                self._consecutive_loss_cooldown_until += timedelta(seconds=self.cfg.consecutive_loss_cooldown_secs)
                logger.critical(
                    f"[RISK] ⚠ 连续亏损 {self._consecutive_losses} 次，"
                    f"触发熔断！冷却至 {self._consecutive_loss_cooldown_until:%H:%M:%S}"
                )

            if self._consecutive_loss_cooldown_until and datetime.now() < self._consecutive_loss_cooldown_until:
                remaining = (self._consecutive_loss_cooldown_until - datetime.now()).total_seconds()
                msg = f"连续亏损熔断中，剩余冷却时间 {remaining/60:.0f} 分钟"
                logger.warning(f"[RISK] {msg}")
                return False, msg
            else:
                # 冷却期结束，重置
                logger.info(f"[RISK] 连续亏损冷却期结束，恢复交易")
                self._consecutive_losses = 0
                self._consecutive_loss_cooldown_until = None

        return True, ""

    # ──────────────── 仓位大小计算 ────────────────

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """
        基于固定风险比例计算仓位（合约张数）。

        公式：
            风险金额   = equity × risk_per_trade
            SL 距离%  = |entry - SL| / entry
            仓位 USDT = 风险金额 / SL距离%

        [NEW] 扣除预估手续费和滑点后的净风险金额：
            预估手续费 = 仓位 USDT × (maker_fee + taker_fee)  # 开仓+平仓
            预估滑点   = 仓位 USDT × slippage_bps / 10000
            净风险金额 = 风险金额 - 预估手续费 - 预估滑点

        [BUG5 修复] 仓位 USDT 不超过 equity × leverage（杠杆名义上限）。
        """
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            logger.error("[RISK] SL距离为0，拒绝开仓")
            return 0.0

        risk_usdt = equity * self.cfg.risk_per_trade
        sl_pct = sl_distance / entry_price

        # [NEW] 迭代计算：先估算仓位，再算手续费/滑点，再调整
        # 第一轮粗略估算
        position_usdt = risk_usdt / sl_pct

        # 预估费用
        est_fees = position_usdt * (self.cfg.maker_fee + self.cfg.taker_fee)
        est_slippage = position_usdt * self.cfg.slippage_bps / 10000
        net_risk = risk_usdt - est_fees - est_slippage

        # 用净风险金额重新计算仓位
        if net_risk > 0:
            position_usdt = net_risk / sl_pct

        # [BUG5] 杠杆名义上限
        max_position_usdt = equity * self.cfg.leverage
        if position_usdt > max_position_usdt:
            logger.warning(
                f"[RISK] 仓位 {position_usdt:.2f} USDT 超过 {self.cfg.leverage}x 上限 "
                f"{max_position_usdt:.2f} USDT，截断至上限"
            )
            position_usdt = max_position_usdt

        contracts = position_usdt / entry_price

        logger.info(
            f"[RISK] 仓位计算 | 权益:{equity:.2f} "
            f"风险:{risk_usdt:.2f}USDT ({self.cfg.risk_per_trade*100:.1f}%) | "
            f"预估费用:{est_fees+est_slippage:.4f}USDT | "
            f"SL:{sl_distance:.2f}({sl_pct*100:.3f}%) | "
            f"仓位:{position_usdt:.2f}USDT | 合约:{contracts:.4f}"
        )
        return round(contracts, 4)

    # ──────────────── TP/SL 计算 ────────────────

    def calculate_tp_sl(
        self,
        entry: float,
        manipulation_extreme: float,
        atr: float,
        direction: str,
    ) -> Tuple[float, float, float]:
        """
        返回 (sl, tp1, tp2)

        SL  = manipulation extreme 外侧 ATR × sl_atr_buffer
        TP1 = entry ± SL距离 × tp1_rr
        TP2 = entry ± SL距离 × tp2_rr
        """
        buffer = atr * self.cfg.sl_atr_buffer

        if direction == "long":
            sl = manipulation_extreme - buffer
            sl_dist = entry - sl
            if sl_dist <= 0:
                sl = entry * 0.995
                sl_dist = entry - sl
            tp1 = entry + sl_dist * self.cfg.tp1_rr
            tp2 = entry + sl_dist * self.cfg.tp2_rr
        else:
            sl = manipulation_extreme + buffer
            sl_dist = sl - entry
            if sl_dist <= 0:
                sl = entry * 1.005
                sl_dist = sl - entry
            tp1 = entry - sl_dist * self.cfg.tp1_rr
            tp2 = entry - sl_dist * self.cfg.tp2_rr

        logger.info(
            f"[RISK] TP/SL | {direction} 入场:{entry:.2f} "
            f"SL:{sl:.2f} TP1:{tp1:.2f}(RR{self.cfg.tp1_rr}) "
            f"TP2:{tp2:.2f}(RR{self.cfg.tp2_rr})"
        )
        return round(sl, 2), round(tp1, 2), round(tp2, 2)

    # ──────────────── 记账 ────────────────

    def record_trade_open(self, record: TradeRecord) -> None:
        """[H3] 存储交易记录，不再丢弃"""
        self._daily_trades += 1
        self._trade_counter += 1
        self._open_records[record.trade_id] = record
        logger.info(
            f"[RISK] 开仓记录 today#{self._daily_trades} trade_id={record.trade_id} | "
            f"剩余次数: {self.cfg.max_daily_trades - self._daily_trades}"
        )

    def record_trade_close(self, trade_id: str, pnl: float) -> None:
        """
        [H3] 关联并更新对应的 TradeRecord。
        [NEW] 计算手续费/滑点后的净 PnL，更新连续亏损计数。
        trade_id 由 executor._on_position_closed 传入。
        """
        record = self._open_records.pop(trade_id, None)
        if record is not None:
            # 计算实际手续费：开仓(taker) + 平仓(taker/maker 混合估算)
            entry_value = record.entry_price * record.contracts
            close_value = (record.entry_price + pnl / record.contracts) * record.contracts if record.contracts > 0 else 0
            fees = entry_value * self.cfg.taker_fee + abs(close_value) * self.cfg.taker_fee
            slippage = entry_value * self.cfg.slippage_bps / 10000

            record.fees_paid = round(fees, 4)
            record.slippage_cost = round(slippage, 4)
            record.pnl = round(pnl, 4)
            record.pnl_after_fees = round(pnl - fees - slippage, 4)
            record.status = "sl" if pnl < 0 else "closed"
            record.closed_at = datetime.now()
            self._closed_records.append(record)

            # [NEW] 更新连续亏损计数
            if pnl < 0:
                self._consecutive_losses += 1
                logger.warning(
                    f"[RISK] 亏损 | 连续亏损: {self._consecutive_losses}/{self.cfg.max_consecutive_losses}"
                )
            else:
                self._consecutive_losses = 0

            logger.info(
                f"[RISK] 平仓记录 trade_id={trade_id} "
                f"毛PnL:{pnl:+.4f} 费用:{fees+slippage:.4f} "
                f"净PnL:{record.pnl_after_fees:+.4f} USDT"
            )

    # ──────────────── 持仓超时检查 ────────────────

    def check_position_timeout(self, trade_id: str) -> Tuple[bool, str]:
        """
        [NEW] 检查持仓是否超过最大允许时间。
        返回 (是否超时, 原因)
        """
        record = self._open_records.get(trade_id)
        if record is None:
            return False, ""

        holding_secs = (datetime.now() - record.opened_at).total_seconds()
        if holding_secs > self.cfg.max_holding_time_secs:
            reason = (
                f"持仓超时 {holding_secs/60:.0f}min > "
                f"{self.cfg.max_holding_time_secs/60:.0f}min"
            )
            logger.warning(f"[RISK] ⚠ {reason}")
            return True, reason
        return False, ""

    # ──────────────── 查询 ────────────────

    @property
    def daily_trades_count(self) -> int:
        return self._daily_trades

    @property
    def daily_trades_remaining(self) -> int:
        return max(0, self.cfg.max_daily_trades - self._daily_trades)

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    def daily_loss_pct(self, current_equity: float) -> float:
        if self._daily_start_equity <= 0:
            return 0.0
        return (self._daily_start_equity - current_equity) / self._daily_start_equity

    def daily_stats_snapshot(self) -> dict:
        """
        [H4] 返回当前交易日统计快照。
        在日切前由主循环调用，记录昨日汇总。
        """
        closed_today = [r for r in self._closed_records if r.closed_at and r.closed_at.date() == self._today]
        wins = sum(1 for r in closed_today if r.pnl > 0)
        total_pnl = sum(r.pnl for r in closed_today)
        total_fees = sum(r.fees_paid + r.slippage_cost for r in closed_today)
        return {
            "date": self._today.isoformat(),
            "trades": self._daily_trades,
            "wins": wins,
            "total_pnl": round(total_pnl, 4),
            "total_pnl_after_fees": round(total_pnl - total_fees, 4),
            "total_fees": round(total_fees, 4),
            "start_equity": self._daily_start_equity,
            "consecutive_losses": self._consecutive_losses,
        }

    def get_closed_records(self) -> List[TradeRecord]:
        """返回所有历史平仓记录（副本）"""
        return list(self._closed_records)

    def get_open_records(self) -> List[TradeRecord]:
        """返回当前持仓中的记录（副本）"""
        return list(self._open_records.values())

    def get_equity_curve(self) -> List[dict]:
        """返回权益曲线数据（用于前端图表）"""
        if not self._closed_records:
            return []
        curve = []
        cumulative = 0.0
        for r in sorted(self._closed_records, key=lambda x: x.closed_at):
            cumulative += r.pnl_after_fees
            curve.append({
                "time": r.closed_at.strftime("%H:%M"),
                "cumulative_pnl": round(cumulative, 4),
                "trade_pnl": round(r.pnl_after_fees, 4),
                "trade_id": r.trade_id,
            })
        return curve
