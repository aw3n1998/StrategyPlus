"""
PO3/AMD 剥头皮策略 — 全局配置（仅支持 Bitget）
"""
from dataclasses import dataclass, field
import os
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()


@dataclass
class PO3Config:
    # ── Bitget 连接（无 exchange 选择器，固定为 Bitget）──
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""      # Bitget 必填 passphrase
    testnet: bool = True
    proxy: str = ""               # HTTP 代理地址，如 "http://127.0.0.1:7897"
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT:USDT"])
    leverage: int = 30             # 建议 25~40

    # ── 保证金模式 ──
    margin_mode: str = "isolated"

    # ── 风险控制 ──
    risk_per_trade: float = 0.01   # 每笔风险占账户净值比例 (1%)
    max_daily_trades: int = 10     # 每日最大交易次数
    max_daily_loss: float = 0.06   # 每日最大亏损比例 (6%)
    max_consecutive_losses: int = 3  # 连续亏损熔断次数
    consecutive_loss_cooldown_secs: int = 7200  # 熔断冷却时间（默认2小时）
    max_holding_time_secs: int = 3600  # 最大持仓时间（默认1小时）

    # ── 手续费 & 滑点 ──
    maker_fee: float = 0.0002      # Maker 手续费 0.02%
    taker_fee: float = 0.0005      # Taker 手续费 0.05%
    slippage_bps: int = 2          # 预估滑点（基点，2 = 0.02%）

    # ── 止盈止损 ──
    tp1_rr: float = 2.2            # 第一目标 RR（平仓 tp1_close_pct 比例）
    tp2_rr: float = 3.0            # 第二目标 RR（trailing stop 跟踪剩余仓位）
    tp1_close_pct: float = 0.5     # 到达 TP1 时平仓 50%
    sl_atr_buffer: float = 0.2     # SL 在 manipulation 极值外侧 ATR*0.2

    # ── PO3 检测参数 ──
    acc_bars: int = 10             # 累积阶段识别所需最小 K 线数
    acc_atr_mult: float = 1.5      # 累积区间高度需 < ATR(14) * 此值
    manip_atr_mult: float = 0.5    # 假突破需超出 range 边界 ATR*此值
    manip_max_age_bars: int = 8    # Manipulation 有效窗口（15m K 线根数）

    # ── 波动率过滤 ──
    volatility_filter_enabled: bool = True
    volatility_atr_daily_threshold: float = 0.05  # 日线 ATR% 超过此值暂停交易（5%）
    volatility_lookback_days: int = 14  # 日线 ATR 计算周期

    # ── Trailing Stop ──
    trailing_atr_mult: float = 1.5  # Trailing stop 距离 = ATR * 此值

    # ── 事件循环间隔（秒）──
    poll_interval_1m: int = 5      # Trailing stop tick 间隔（秒）

    # ── 日志 ──
    log_level: str = "INFO"
    quiet_mode: bool = False       # 精简模式，只输出信号和交易事件

    # ── 紧急平仓确认 ──
    emergency_close_delay_secs: int = 10  # 紧急平仓延迟秒数（可取消）

    # ── API 服务 ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── 模拟交易 ──
    simulated_equity: float = 10000.0   # 模拟模式初始资金（总账户）
    # 每个策略独立的模拟资金 {"po3": 1000, "orderflow": 1000}
    strategy_capitals: Dict[str, float] = field(default_factory=dict)

    # ── 兼容旧版 symbol 字段 ──
    @property
    def symbol(self) -> str:
        return self.symbols[0] if self.symbols else "BTC/USDT:USDT"


def load_config() -> PO3Config:
    """从环境变量加载配置"""
    symbols_raw = os.getenv("PO3_SYMBOLS", os.getenv("PO3_SYMBOL", "BTC/USDT:USDT"))
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]

    return PO3Config(
        api_key=os.getenv("PO3_API_KEY", ""),
        api_secret=os.getenv("PO3_API_SECRET", ""),
        api_passphrase=os.getenv("PO3_API_PASSPHRASE", ""),
        testnet=os.getenv("PO3_TESTNET", "true").lower() == "true",
        proxy=os.getenv("PO3_PROXY", ""),
        symbols=symbols,
        leverage=int(os.getenv("PO3_LEVERAGE", "30")),
        margin_mode=os.getenv("PO3_MARGIN_MODE", "isolated"),
        risk_per_trade=float(os.getenv("PO3_RISK_PER_TRADE", "0.01")),
        max_daily_trades=int(os.getenv("PO3_MAX_DAILY_TRADES", "10")),
        max_daily_loss=float(os.getenv("PO3_MAX_DAILY_LOSS", "0.06")),
        max_consecutive_losses=int(os.getenv("PO3_MAX_CONSECUTIVE_LOSSES", "3")),
        consecutive_loss_cooldown_secs=int(os.getenv("PO3_CONSECUTIVE_LOSS_COOLDOWN", "7200")),
        max_holding_time_secs=int(os.getenv("PO3_MAX_HOLDING_TIME", "3600")),
        maker_fee=float(os.getenv("PO3_MAKER_FEE", "0.0002")),
        taker_fee=float(os.getenv("PO3_TAKER_FEE", "0.0005")),
        slippage_bps=int(os.getenv("PO3_SLIPPAGE_BPS", "2")),
        tp1_rr=float(os.getenv("PO3_TP1_RR", "2.2")),
        tp2_rr=float(os.getenv("PO3_TP2_RR", "3.0")),
        tp1_close_pct=float(os.getenv("PO3_TP1_CLOSE_PCT", "0.5")),
        sl_atr_buffer=float(os.getenv("PO3_SL_ATR_BUFFER", "0.2")),
        acc_bars=int(os.getenv("PO3_ACC_BARS", "10")),
        acc_atr_mult=float(os.getenv("PO3_ACC_ATR_MULT", "1.5")),
        manip_atr_mult=float(os.getenv("PO3_MANIP_ATR_MULT", "0.5")),
        manip_max_age_bars=int(os.getenv("PO3_MANIP_MAX_AGE_BARS", "8")),
        volatility_filter_enabled=os.getenv("PO3_VOL_FILTER", "true").lower() == "true",
        volatility_atr_daily_threshold=float(os.getenv("PO3_VOL_ATR_THRESHOLD", "0.05")),
        volatility_lookback_days=int(os.getenv("PO3_VOL_LOOKBACK", "14")),
        trailing_atr_mult=float(os.getenv("PO3_TRAILING_ATR_MULT", "1.5")),
        poll_interval_1m=int(os.getenv("PO3_POLL_1M", "5")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        quiet_mode=os.getenv("PO3_QUIET", "false").lower() == "true",
        emergency_close_delay_secs=int(os.getenv("PO3_EMERGENCY_DELAY", "10")),
        api_host=os.getenv("PO3_API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("PO3_API_PORT", "8000")),
        simulated_equity=float(os.getenv("PO3_SIMULATED_EQUITY", "10000")),
        strategy_capitals=_parse_strategy_capitals(),
    )

def _parse_strategy_capitals() -> Dict[str, float]:
    """解析策略资金配置，格式: po3:1000,orderflow:1000"""
    raw = os.getenv("PO3_STRATEGY_CAPITALS", "po3:1000,orderflow:1000")
    result = {}
    for item in raw.split(","):
        if ":" in item:
            sid, cap = item.strip().split(":")
            result[sid] = float(cap)
    return result
