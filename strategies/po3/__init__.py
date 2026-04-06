"""
PO3/AMD 策略

基于 K 线形态的三阶段剥头皮策略：
- Accumulation (累积阶段)
- Manipulation (假突破)
- Distribution (派发)

时间框架：15m + 1m 组合
"""
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from strategies.base import BaseStrategy, MarketEvent, StrategyConfig
from core.detector import PO3Detector, ManipulationEvent
from core.executor import PO3Executor
from core.risk_manager import RiskManager
from core.logger import TradeLogger
from config.settings import PO3Config


class PO3Strategy(BaseStrategy):
    """
    PO3/AMD 剥头皮策略
    
    继承自 BaseStrategy，与其他策略共享同一市场数据源
    """
    
    def __init__(self, config: PO3Config, exchange, symbols: list, dry_run: bool = False):
        # 构建 StrategyConfig
        sc = StrategyConfig(
            leverage=config.leverage,
            risk_per_trade=config.risk_per_trade,
            tp1_rr=config.tp1_rr,
            tp2_rr=config.tp2_rr,
            max_daily_trades=config.max_daily_trades,
            max_consecutive_losses=config.max_consecutive_losses,
        )
        super().__init__(sc, exchange, symbols, dry_run)
        
        self.cfg = config
        
        # 每个 symbol 独立的组件
        self.detectors: Dict[str, PO3Detector] = {}
        self.risks: Dict[str, RiskManager] = {}
        self.executors: Dict[str, PO3Executor] = {}
        self.trade_logger = TradeLogger()
        
        # 当前 detected manipulation
        self._current_manip: Dict[str, Optional[ManipulationEvent]] = {s: None for s in symbols}
        
        for symbol in symbols:
            self.detectors[symbol] = PO3Detector(config)
            self.risks[symbol] = RiskManager(config)
            self.executors[symbol] = PO3Executor(
                exchange, config, self.risks[symbol], self.trade_logger, dry_run=dry_run
            )
    
    @property
    def id(self) -> str:
        return "po3"
    
    @property
    def name(self) -> str:
        return "PO3/AMD"
    
    @property
    def description(self) -> str:
        return "剥头皮策略 - 基于 K 线形态的突破交易"
    
    async def on_15m_candle(self, event: MarketEvent):
        """15分钟K线收盘 - 检测 Accumulation / Manipulation"""
        if event.df_15m is None or event.df_15m.empty:
            return
        
        symbol = event.symbol
        detector = self.detectors.get(symbol)
        executor = self.executors.get(symbol)
        
        if not detector or not executor:
            return
        
        # 只处理有持仓的情况
        if not executor.is_in_position:
            # 检测 Accumulation
            acc = detector.detect_accumulation(event.df_15m)
            if acc:
                logger.info(f"[PO3-{symbol}] Accumulation: {acc.bar_count} bars")
            
            # 检测 Manipulation
            manip = detector.detect_manipulation(event.df_15m, acc)
            if manip:
                self._current_manip[symbol] = manip
                logger.info(f"[PO3-{symbol}] Manipulation: {manip.bias}, {manip.extreme:.2f}")
    
    async def on_1m_candle(self, event: MarketEvent):
        """1分钟K线收盘 - 检测入场信号"""
        if event.df_1m is None or event.df_1m.empty:
            return
        
        symbol = event.symbol
        detector = self.detectors.get(symbol)
        executor = self.executors.get(symbol)
        risk = self.risks.get(symbol)
        
        if not detector or not executor or not risk:
            return
        
        manip = self._current_manip.get(symbol)
        
        # 只有在有 manipulation 且不在持仓中时才检测入场
        if manip and not executor.is_in_position:
            entry = detector.detect_entry_signal(event.df_1m, manip)
            if entry:
                direction = "long" if entry.direction == "bullish" else "short"
                
                logger.info(f"[PO3-{symbol}] 入场: {direction}, entry={entry.entry_price:.2f}")
                
                # 检查风控
                if risk.can_trade():
                    if risk.check_risk():
                        await executor.open_position(
                            symbol=symbol,
                            direction=direction,
                            entry_price=entry.entry_price,
                            stop_loss=entry.stop_loss,
                            tp1=entry.tp1,
                            tp2=entry.tp2,
                        )
    
    async def on_tick(self, event: MarketEvent):
        """实时tick - 管理持仓"""
        symbol = event.symbol
        executor = self.executors.get(symbol)
        
        if executor and executor.is_in_position:
            await executor.update_trailing_stop(event.price)
            await executor.check_exit_conditions(event.price)
    
    def get_status(self) -> Dict:
        """获取策略状态"""
        status = {}
        for symbol in self.symbols:
            executor = self.executors.get(symbol)
            risk = self.risks.get(symbol)
            
            status[symbol] = {
                "in_position": executor.is_in_position if executor else False,
                "manipulation": self._current_manip.get(symbol).__dict__ if self._current_manip.get(symbol) else None,
                "consecutive_losses": risk.consecutive_losses if risk else 0,
            }
        return status
