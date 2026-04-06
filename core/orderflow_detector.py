"""
订单流检测器

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


@dataclass
class OrderBlock:
    """订单块"""
    high: float
    low: float
    direction: str
    strength: float
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class Signal:
    """订单流信号"""
    type: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    confidence: float
    reason: str


class OrderFlowDetector:
    """订单流检测器"""
    
    def __init__(self, cfg):
        self.cfg = cfg
        self.order_blocks: List[OrderBlock] = []
        self.last_signal_bar: Optional[datetime] = None
        self.ob_lookback = 10
        self.liq_lookback = 5
        self.min_volume_mult = 1.5
    
    def detect_order_blocks(self, df: pd.DataFrame) -> List[OrderBlock]:
        """检测订单块"""
        if len(df) < self.ob_lookback + 5:
            return []
        
        blocks = []
        for i in range(len(df) - self.ob_lookback, len(df) - 5):
            recent = df.iloc[i:i+5]
            if len(recent) < 3:
                continue
            
            for j in range(i, min(i + 3, len(df) - 1)):
                candle = df.iloc[j]
                next_candles = df.iloc[j+1:j+4]
                
                if len(next_candles) < 2:
                    continue
                
                if candle['close'] > candle['open'] and self._is_high_volume(candle, df):
                    if all(next_candles['low'] >= candle['low']):
                        blocks.append(OrderBlock(
                            high=candle['high'],
                            low=candle['low'],
                            direction='bull',
                            strength=self._calculate_strength(candle, df)
                        ))
                elif candle['close'] < candle['open'] and self._is_high_volume(candle, df):
                    if all(next_candles['high'] <= candle['high']):
                        blocks.append(OrderBlock(
                            high=candle['high'],
                            low=candle['low'],
                            direction='bear',
                            strength=self._calculate_strength(candle, df)
                        ))
        
        self.order_blocks = blocks[-3:] if len(blocks) > 3 else blocks
        return self.order_blocks
    
    def detect_liquidity_sweep(self, df: pd.DataFrame) -> Optional[Signal]:
        """检测流动性扫取"""
        if len(df) < self.liq_lookback + 2:
            return None
        
        recent = df.tail(self.liq_lookback)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        if prev_candle['high'] > swing_high:
            if last_candle['close'] < last_candle['open'] and last_candle['high'] > prev_candle['high']:
                if last_candle['volume'] < prev_candle['volume'] * 0.7:
                    return Signal(
                        type='liquidity_sweep',
                        direction='short',
                        entry_price=last_candle['close'],
                        stop_loss=last_candle['high'] * 1.002,
                        tp1=last_candle['close'] - (last_candle['close'] - swing_low) * 0.5,
                        tp2=swing_low,
                        confidence=0.7,
                        reason=f'Liquidity sweep at {swing_high:.2f}'
                    )
        
        if prev_candle['low'] < swing_low:
            if last_candle['close'] > last_candle['open'] and last_candle['low'] < prev_candle['low']:
                if last_candle['volume'] < prev_candle['volume'] * 0.7:
                    return Signal(
                        type='liquidity_sweep',
                        direction='long',
                        entry_price=last_candle['close'],
                        stop_loss=last_candle['low'] * 0.998,
                        tp1=last_candle['close'] + (swing_high - last_candle['close']) * 0.5,
                        tp2=swing_high,
                        confidence=0.7,
                        reason=f'Liquidity sweep at {swing_low:.2f}'
                    )
        
        return None
    
    def detect_imbalance(self, df: pd.DataFrame) -> Optional[Signal]:
        """检测失衡区"""
        if len(df) < 10:
            return None
        
        recent = df.tail(5)
        
        if recent['close'].iloc[-1] > recent['open'].iloc[0]:
            move = recent['close'].iloc[-1] - recent['open'].iloc[0]
            retracement = (recent['high'].max() - recent['close'].iloc[-1]) / move
            
            if 0.382 < retracement < 0.618:
                if recent['volume'].iloc[-1] < recent['volume'].mean() * 0.6:
                    return Signal(
                        type='imbalance',
                        direction='long',
                        entry_price=recent['close'].iloc[-1],
                        stop_loss=recent['low'].min() * 0.998,
                        tp1=recent['close'].iloc[-1] + move * 0.382,
                        tp2=recent['close'].iloc[-1] + move * 0.618,
                        confidence=0.6,
                        reason=f'Bullish imbalance: {retracement*100:.1f}% retracement'
                    )
        elif recent['close'].iloc[-1] < recent['open'].iloc[0]:
            move = recent['open'].iloc[0] - recent['close'].iloc[-1]
            retracement = (recent['close'].iloc[-1] - recent['low'].min()) / move
            
            if 0.382 < retracement < 0.618:
                if recent['volume'].iloc[-1] < recent['volume'].mean() * 0.6:
                    return Signal(
                        type='imbalance',
                        direction='short',
                        entry_price=recent['close'].iloc[-1],
                        stop_loss=recent['high'].max() * 1.002,
                        tp1=recent['close'].iloc[-1] - move * 0.382,
                        tp2=recent['close'].iloc[-1] - move * 0.618,
                        confidence=0.6,
                        reason=f'Bearish imbalance: {retracement*100:.1f}% retracement'
                    )
        
        return None
    
    def detect_absorption(self, df: pd.DataFrame) -> Optional[Signal]:
        """检测吸收"""
        if len(df) < 5:
            return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        candle_range = abs(last['close'] - last['open'])
        avg_range = df.tail(5)['close'].diff().abs().mean()
        
        if last['volume'] > prev['volume'] * 2 and candle_range < avg_range * 0.3:
            if last['close'] > last['open']:
                return Signal(
                    type='absorption',
                    direction='long',
                    entry_price=last['close'],
                    stop_loss=last['low'] * 0.998,
                    tp1=last['close'] + avg_range,
                    tp2=last['close'] + avg_range * 2,
                    confidence=0.65,
                    reason='Absorption: high volume, low price movement'
                )
            else:
                return Signal(
                    type='absorption',
                    direction='short',
                    entry_price=last['close'],
                    stop_loss=last['high'] * 1.002,
                    tp1=last['close'] - avg_range,
                    tp2=last['close'] - avg_range * 2,
                    confidence=0.65,
                    reason='Absorption: high volume, low price movement'
                )
        
        return None
    
    def detect_all_signals(self, df: pd.DataFrame) -> List[Signal]:
        """检测所有信号"""
        signals = []
        
        self.detect_order_blocks(df)
        
        liq_signal = self.detect_liquidity_sweep(df)
        if liq_signal:
            signals.append(liq_signal)
        
        imb_signal = self.detect_imbalance(df)
        if imb_signal:
            signals.append(imb_signal)
        
        abs_signal = self.detect_absorption(df)
        if abs_signal:
            signals.append(abs_signal)
        
        signals.sort(key=lambda x: x.confidence, reverse=True)
        
        if signals and self.last_signal_bar is not None:
            if df.index[-1] == self.last_signal_bar:
                return signals[:1]
        
        return signals
    
    def _is_high_volume(self, candle, df: pd.DataFrame) -> bool:
        avg_vol = df['volume'].tail(20).mean()
        return candle['volume'] > avg_vol * self.min_volume_mult
    
    def _calculate_strength(self, candle, df: pd.DataFrame) -> float:
        avg_vol = df['volume'].tail(20).mean()
        vol_ratio = candle['volume'] / avg_vol if avg_vol > 0 else 1
        range_ratio = abs(candle['close'] - candle['open']) / df['close'].tail(20).std()
        return min(vol_ratio * range_ratio / 2, 1.0)
