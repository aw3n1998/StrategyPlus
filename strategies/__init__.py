"""
策略管理器 - 一对多架构

统一管理所有策略，共享同一个数据源
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime

import ccxt.pro as ccxtpro
from loguru import logger

from strategies.base import BaseStrategy, MarketEvent
from config.settings import PO3Config


class StrategyManager:
    """
    策略管理器
    
    负责：
    - 维护单一 DataFeed
    - 注册/注销策略
    - 将市场事件分发给所有策略
    """
    
    def __init__(self, exchange: ccxtpro.Exchange, symbols: List[str], config: PO3Config):
        self.exchange = exchange
        self.symbols = symbols
        self.config = config
        self.strategies: Dict[str, BaseStrategy] = {}
        
        # 共享数据源
        from core.data_feed import DataFeed
        self.feed = DataFeed(exchange, symbols)
        
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    def register_strategy(self, strategy: BaseStrategy):
        """注册策略"""
        if strategy.id in self.strategies:
            logger.warning(f"策略 {strategy.id} 已注册，跳过")
            return
        
        self.strategies[strategy.id] = strategy
        logger.info(f"[StrategyManager] 注册策略: {strategy.name}, 标的: {self.symbols}")
    
    def unregister_strategy(self, strategy_id: str):
        """注销策略"""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            logger.info(f"[StrategyManager] 注销策略: {strategy_id}")
    
    async def start(self):
        """启动策略管理器"""
        self._running = True
        
        # 启动共享数据源
        await self.feed.start()
        
        # 启动所有策略
        for strategy in self.strategies.values():
            await strategy.start()
        
        # 为每个symbol创建事件分发任务
        for symbol in self.symbols:
            self._tasks.append(asyncio.create_task(self._dispatch_15m(symbol)))
            self._tasks.append(asyncio.create_task(self._dispatch_1m(symbol)))
            self._tasks.append(asyncio.create_task(self._dispatch_tick(symbol)))
        
        logger.info(f"[StrategyManager] 启动，共 {len(self.strategies)} 个策略")
    
    async def stop(self):
        """停止策略管理器"""
        self._running = False
        
        # 停止所有策略
        for strategy in self.strategies.values():
            await strategy.stop()
        
        # 停止数据源
        await self.feed.stop()
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
        
        logger.info("[StrategyManager] 已停止")
    
    async def _dispatch_15m(self, symbol: str):
        """分发15分钟K线事件"""
        event = asyncio.Event()
        self.feed.candle_closed_15m[symbol] = event
        
        while self._running:
            await event.wait()
            event.clear()
            
            event_data = MarketEvent(
                symbol=symbol,
                timestamp=datetime.now(),
                price=self.feed.last_price.get(symbol, 0),
                df_15m=self.feed.get_df_15m(symbol),
            )
            
            tasks = []
            for strategy in self.strategies.values():
                tasks.append(asyncio.create_task(strategy.on_15m_candle(event_data)))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _dispatch_1m(self, symbol: str):
        """分发1分钟K线事件"""
        event = asyncio.Event()
        self.feed.candle_closed_1m[symbol] = event
        
        while self._running:
            await event.wait()
            event.clear()
            
            event_data = MarketEvent(
                symbol=symbol,
                timestamp=datetime.now(),
                price=self.feed.last_price.get(symbol, 0),
                df_1m=self.feed.get_df_1m(symbol),
            )
            
            tasks = []
            for strategy in self.strategies.values():
                tasks.append(asyncio.create_task(strategy.on_1m_candle(event_data)))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _dispatch_tick(self, symbol: str):
        """分发实时tick事件"""
        while self._running:
            await asyncio.sleep(5)
            
            event_data = MarketEvent(
                symbol=symbol,
                timestamp=datetime.now(),
                price=self.feed.last_price.get(symbol, 0),
                ticker=self.feed.last_price,
            )
            
            tasks = []
            for strategy in self.strategies.values():
                tasks.append(asyncio.create_task(strategy.on_tick(event_data)))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_all_status(self) -> Dict:
        """获取所有策略状态"""
        status = {}
        for strategy_id, strategy in self.strategies.items():
            status[strategy_id] = strategy.get_status()
        return status
    
    @property
    def active_strategies(self) -> List[str]:
        return list(self.strategies.keys())
