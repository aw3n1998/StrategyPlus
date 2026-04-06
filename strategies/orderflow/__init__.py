"""
订单流 + 资金流策略

核心逻辑：
1. 订单块 (Order Block) - 识别大型机构的订单区域
2. 流动性扫取 (Liquidity Sweep) - 突破前高/前低后的反转
3. 失衡区 (Imbalance) - 快速移动后的回撤区域
4. 吸收区域 (Absorption) - 大额成交但价格不动
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy, MarketEvent, StrategyConfig
from core.orderflow_detector import OrderFlowDetector, Signal as OFSignal
from core.executor import PO3Executor
from core.risk_manager import RiskManager
from core.logger import TradeLogger
from config.settings import PO3Config


class OrderFlowStrategy(BaseStrategy):
    """
    订单流 + 资金流策略
    
    基于订单块、流动性扫取、失衡区、吸收区域进行交易
    """
    
    def __init__(self, config: PO3Config, exchange, symbols: list, dry_run: bool = False):
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
        self.detectors: Dict[str, OrderFlowDetector] = {}
        self.risks: Dict[str, RiskManager] = {}
        self.executors: Dict[str, PO3Executor] = {}
        self.trade_logger = TradeLogger()
        
        # 当前信号
        self._current_signals: Dict[str, Optional[OFSignal]] = {s: None for s in symbols}
        
        for symbol in symbols:
            self.detectors[symbol] = OrderFlowDetector(config)
            self.risks[symbol] = RiskManager(config)
            self.executors[symbol] = PO3Executor(
                exchange, config, self.risks[symbol], self.trade_logger, dry_run=dry_run
            )
    
    @property
    def id(self) -> str:
        return "orderflow"
    
    @property
    def name(self) -> str:
        return "Order Flow"
    
    @property
    def description(self) -> str:
        return "订单流+资金流 - 订单块/流动性扫取/失衡区/吸收"
    
    async def on_15m_candle(self, event: MarketEvent):
        """15分钟K线 - 可用于更高时间框架确认"""
        pass
    
    async def on_1m_candle(self, event: MarketEvent):
        """1分钟K线 - 订单流信号检测"""
        if event.df_1m is None or event.df_1m.empty:
            return
        
        symbol = event.symbol
        detector = self.detectors.get(symbol)
        executor = self.executors.get(symbol)
        risk = self.risks.get(symbol)
        
        if not detector or not executor or not risk:
            return
        
        # 只在空仓时检测信号
        if not executor.is_in_position:
            signals = detector.detect_all_signals(event.df_1m)
            
            if signals:
                best_signal = signals[0]
                self._current_signals[symbol] = best_signal
                
                logger.info(f"[OF-{symbol}] 信号: {best_signal.type} {best_signal.direction}")
                
                if risk.can_trade() and risk.check_risk():
                    await executor.open_position(
                        symbol=symbol,
                        direction=best_signal.direction,
                        entry_price=best_signal.entry_price,
                        stop_loss=best_signal.stop_loss,
                        tp1=best_signal.tp1,
                        tp2=best_signal.tp2,
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
            
            signal = self._current_signals.get(symbol)
            
            status[symbol] = {
                "in_position": executor.is_in_position if executor else False,
                "signal": {
                    "type": signal.type if signal else None,
                    "direction": signal.direction if signal else None,
                    "confidence": signal.confidence if signal else None,
                } if signal else None,
                "consecutive_losses": risk.consecutive_losses if risk else 0,
            }
        return status
