"""
策略基类 - 所有策略的父类

定义策略接口，确保统一的事件驱动模式
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd


@dataclass
class MarketEvent:
    """市场事件 - 所有策略共享"""
    symbol: str
    timestamp: datetime
    price: float
    df_15m: Optional[pd.DataFrame] = None
    df_1m: Optional[pd.DataFrame] = None
    ticker: Dict = field(default_factory=dict)


@dataclass
class StrategyConfig:
    """策略配置"""
    leverage: int = 30
    risk_per_trade: float = 0.01
    tp1_rr: float = 2.0
    tp2_rr: float = 3.0
    max_daily_trades: int = 10
    max_consecutive_losses: int = 3


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, config: StrategyConfig, exchange, symbols: List[str], dry_run: bool = False):
        self.config = config
        self.exchange = exchange
        self.symbols = symbols
        self.dry_run = dry_run
        
        self._running = False
        self._current_signals: Dict[str, Any] = {}
    
    @property
    @abstractmethod
    def id(self) -> str:
        """策略ID"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """策略描述"""
        pass
    
    @abstractmethod
    async def on_15m_candle(self, event: MarketEvent):
        """15分钟K线收盘事件"""
        pass
    
    @abstractmethod
    async def on_1m_candle(self, event: MarketEvent):
        """1分钟K线收盘事件"""
        pass
    
    @abstractmethod
    async def on_tick(self, event: MarketEvent):
        """实时tick事件"""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict:
        """获取策略状态"""
        pass
    
    async def start(self):
        """策略启动（可选实现）"""
        self._running = True
    
    async def stop(self):
        """策略停止（可选实现）"""
        self._running = False
    
    @property
    def is_running(self) -> bool:
        return self._running
