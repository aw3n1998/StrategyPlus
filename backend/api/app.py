"""
PO3/AMD 量化交易 API 服务 (FastAPI)

提供 REST API 供前端 Dashboard 使用：
    GET  /api/overview          - 全局概览
    GET  /api/status            - 机器人实时状态
    GET  /api/trades            - 交易历史
    GET  /api/equity-curve      - 权益曲线
    GET  /api/volatility        - 波动率状态
    GET  /api/config            - 当前配置
    POST /api/config/reload     - 热重载配置
    POST /api/emergency/cancel  - 取消紧急平仓
    GET  /api/backtest/results  - 回测结果列表
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from loguru import logger

# ── 全局状态（由 main.py 注入）──
_bot_instance = None
_config = None
_risk_managers: dict = {}
_feed = None
_vol_filter = None
_executors: dict = {}

app = FastAPI(title="PO3/AMD Trading API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def set_bot_instance(bot, cfg, risk_managers, feed, vol_filter, executors):
    """注入机器人实例（由 main.py 调用）"""
    global _bot_instance, _config, _risk_managers, _feed, _vol_filter, _executors
    _bot_instance = bot
    _config = cfg
    _risk_managers = risk_managers
    _feed = feed
    _vol_filter = vol_filter
    _executors = executors


# ──────────────────── API 路由 ────────────────────


@app.get("/api/overview")
async def get_overview():
    """全局概览 - 按策略分开统计"""
    if not _bot_instance:
        raise HTTPException(status_code=503, detail="机器人未启动")

    strategy_stats = {}
    
    risk_managers = _risk_managers
    if not isinstance(risk_managers, dict):
        if hasattr(risk_managers, 'daily_stats_snapshot'):
            sym = _config.symbol if _config else "UNKNOWN"
            risk_managers = {sym: risk_managers}
    
    if isinstance(risk_managers, dict):
        for key, r in risk_managers.items():
            if hasattr(r, 'daily_stats_snapshot'):
                if isinstance(key, tuple):
                    strategy_id, sym = key
                else:
                    sym = key
                    strategy_id = "po3"
                if strategy_id not in strategy_stats:
                    strategy_stats[strategy_id] = {
                        "total_pnl": 0.0,
                        "total_trades": 0,
                        "total_wins": 0,
                        "symbols": [],
                    }
                snap = r.daily_stats_snapshot()
                strategy_stats[strategy_id]["total_pnl"] += snap.get("total_pnl_after_fees", 0)
                strategy_stats[strategy_id]["total_trades"] += snap["trades"]
                strategy_stats[strategy_id]["total_wins"] += snap["wins"]
                if sym not in strategy_stats[strategy_id]["symbols"]:
                    strategy_stats[strategy_id]["symbols"].append(sym)

    active_positions = 0
    executors = _executors
    if not isinstance(executors, dict):
        if hasattr(executors, 'is_in_position') and executors.is_in_position:
            active_positions = 1
        executors = {_config.symbol if _config else "UNKNOWN": executors}
    
    if isinstance(executors, dict):
        for e in executors.values():
            if hasattr(e, 'is_in_position') and e.is_in_position:
                active_positions += 1
            if hasattr(e, 'is_in_position') and e.is_in_position:
                active_positions += 1

    # 计算每个策略的 win_rate 和 capital
    for sid in strategy_stats:
        stats = strategy_stats[sid]
        stats["win_rate"] = round((stats["total_wins"] / stats["total_trades"] * 100), 1) if stats["total_trades"] > 0 else 0
        stats["total_pnl"] = round(stats["total_pnl"], 2)
        stats["simulated_capital"] = _STRATEGIES.get(sid, {}).get("simulated_capital", 1000.0)

    total_pnl = sum(s["total_pnl"] for s in strategy_stats.values())
    total_trades = sum(s["total_trades"] for s in strategy_stats.values())
    total_capital = sum(s["simulated_capital"] for s in strategy_stats.values())

    return {
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "active_positions": active_positions,
        "symbols": list(set(s for stats in strategy_stats.values() for s in stats["symbols"])),
        "running": _bot_instance._running,
        "dry_run": _bot_instance.dry_run if _bot_instance else True,
        "strategies": _ACTIVE_STRATEGIES,
        "strategy_stats": strategy_stats,
        "total_capital": total_capital,
    }


@app.get("/api/status")
async def get_status():
    """各标的实时状态"""
    if not _bot_instance:
        raise HTTPException(status_code=503, detail="机器人未启动")

    result = {}
    # 兼容新旧格式：dict 或单个对象
    symbols = _config.symbols if isinstance(_config.symbols, list) else [_config.symbols] if _config else [_config.symbol]
    
    # 获取 executors（可能是 dict 或单个对象）
    exe = _executors
    
    # 处理单个对象的情况
    executors = _executors
    if not isinstance(executors, dict):
        # 单个 executor - 创建一个 dict 以统一处理
        symbol = _config.symbol if _config else "UNKNOWN"
        executors = {symbol: executors} if hasattr(executors, 'position') else {}
    
    risk_managers = _risk_managers
    if not isinstance(risk_managers, dict):
        if hasattr(risk_managers, 'daily_stats_snapshot'):
            symbol = _config.symbol if _config else "UNKNOWN"
            risk_managers = {symbol: risk_managers}
    
    current_manip = _bot_instance._current_manip if _bot_instance else None
    if current_manip and not isinstance(current_manip, dict):
        # 单个 manipulation 对象 - 包装为 dict
        symbol = _config.symbol if _config else "UNKNOWN"
        current_manip = {symbol: current_manip}
    
    # 判断是否是单个 executor（通过检查是否有 position 属性）
    is_single_executor = hasattr(_executors, 'position') and not isinstance(_executors, dict)
    
    if is_single_executor:
        # 单个 executor 格式（每个 symbol 用同一个 executor）
        for symbol in symbols:
            exe = _executors
            risk = _risk_managers if not isinstance(_risk_managers, dict) else _risk_managers.get(symbol)
            price = _feed.last_price.get(symbol, 0) if _feed and hasattr(_feed, 'last_price') else 0

            pos = None
            if exe and exe.position:
                p = exe.position
                pos = {
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": price,
                    "contracts": p.contracts_remaining,
                    "stop_loss": p.stop_loss,
                    "tp1": p.tp1,
                    "tp2": p.tp2,
                    "tp1_pnl": p.tp1_pnl,
                    "state": exe.state.value,
                    "holding_secs": (datetime.now() - p.opened_at).total_seconds(),
                }

            ws_health = {}
            if _feed and hasattr(_feed, 'ws_health'):
                ws_health = _feed.ws_health(symbol)

            manip = None
            if _bot_instance._current_manip:
                m = _bot_instance._current_manip
                if m:
                    manip = {
                        "bias": m.bias,
                        "direction": m.direction,
                        "extreme": m.extreme,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    }

            equity = None
            if risk and hasattr(risk, 'daily_stats_snapshot'):
                snap = risk.daily_stats_snapshot()
                equity = {
                    "start_equity": snap.get("start_equity", 0),
                    "total_pnl": snap.get("total_pnl", 0),
                    "trades": snap.get("trades", 0),
                }

            result[symbol] = {
                "position": pos,
                "manipulation": manip,
                "equity": equity,
                "price": price,
                "ws_health": ws_health,
            }
    else:
        # dict 格式（新格式）
        for symbol in symbols:
            exe = executors.get(symbol)
            risk = risk_managers.get(symbol)
            price = _feed.last_price.get(symbol, 0) if _feed else 0

            pos = None
            if exe and exe.position:
                p = exe.position
                pos = {
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": price,
                    "contracts": p.contracts_remaining,
                    "stop_loss": p.stop_loss,
                    "tp1": p.tp1,
                    "tp2": p.tp2,
                    "tp1_pnl": p.tp1_pnl,
                    "state": exe.state.value,
                    "holding_secs": (datetime.now() - p.opened_at).total_seconds(),
                }

            ws_health = {}
            if _feed:
                ws_health = _feed.ws_health(symbol)

            manip = None
            if current_manip and current_manip.get(symbol):
                m = current_manip[symbol]
                manip = {
                    "bias": m.bias,
                    "direction": m.direction,
                    "extreme": m.extreme,
                }

            risk_snap = risk.daily_stats_snapshot() if risk else {}

            result[symbol] = {
                "price": price,
                "position": pos,
                "manipulation": manip,
                "ws_health": ws_health,
                "daily_stats": risk_snap,
                "consecutive_losses": risk.consecutive_losses if risk and hasattr(risk, 'consecutive_losses') else 0,
            }

    return result


@app.get("/api/trades")
async def get_trades(symbol: Optional[str] = None, limit: int = 50):
    """交易历史"""
    if not _risk_managers:
        raise HTTPException(status_code=503, detail="机器人未启动")

    all_trades = []
    # 兼容新旧格式：{(strategy_id, symbol): RiskManager} 或 {symbol: RiskManager} 或单个对象
    risk_managers = _risk_managers
    
    # 处理单个对象的情况
    if not isinstance(risk_managers, dict):
        if hasattr(risk_managers, 'get_closed_records'):
            risk_managers = {(_config.symbol if _config else "UNKNOWN"): risk_managers}
    
    for key, risk in risk_managers.items():
        if isinstance(key, tuple):
            sym = key[1]
        else:
            sym = key
        if symbol and sym != symbol:
            continue
        for r in risk.get_closed_records():
                all_trades.append({
                    "symbol": sym,
                    "trade_id": r.trade_id,
                    "direction": r.direction,
                    "entry_price": r.entry_price,
                    "exit_price": r.entry_price + r.pnl / r.contracts if r.contracts > 0 else 0,
                    "pnl": r.pnl,
                    "pnl_after_fees": r.pnl_after_fees,
                    "fees_paid": r.fees_paid,
                    "slippage_cost": r.slippage_cost,
                    "status": r.status,
                    "opened_at": r.opened_at.isoformat(),
                    "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                    "holding_secs": (r.closed_at - r.opened_at).total_seconds() if r.closed_at else 0,
                })

    all_trades.sort(key=lambda x: x["closed_at"] or "", reverse=True)
    return all_trades[:limit]


@app.get("/api/equity-curve")
async def get_equity_curve(symbol: Optional[str] = None):
    """权益曲线"""
    if not _risk_managers:
        raise HTTPException(status_code=503, detail="机器人未启动")

    result = {}
    risk_managers = _risk_managers
    
    # 处理单个对象的情况
    if not isinstance(risk_managers, dict):
        if hasattr(risk_managers, 'get_equity_curve'):
            risk_managers = {(_config.symbol if _config else "UNKNOWN"): risk_managers}

    for key, risk in risk_managers.items():
        if isinstance(key, tuple):
            sid, sym = key
        else:
            sym = key
            sid = "po3"
        if symbol and sym != symbol:
            continue
        if risk:
            result[f"{sid}:{sym}"] = risk.get_equity_curve()
    return result


@app.get("/api/equity-curve-by-strategy")
async def get_equity_curve_by_strategy():
    """按策略分开的权益曲线"""
    if not _risk_managers:
        raise HTTPException(status_code=503, detail="机器人未启动")

    result = {}
    risk_managers = _risk_managers
    
    # 处理单个对象的情况
    if not isinstance(risk_managers, dict):
        if hasattr(risk_managers, 'get_equity_curve'):
            risk_managers = {(_config.symbol if _config else "UNKNOWN"): risk_managers}

    for key, risk in risk_managers.items():
        if isinstance(key, tuple):
            sid, sym = key
        else:
            sym = key
            sid = "po3"
        if sid not in result:
            result[sid] = []
        curve = risk.get_equity_curve()
        for point in curve:
            point["symbol"] = sym
        result[sid].extend(curve)
    
    # 每个策略内按时间排序
    for sid in result:
        result[sid] = sorted(result[sid], key=lambda x: x.get("time", ""))
    
    return result


@app.get("/api/volatility")
async def get_volatility():
    """波动率状态"""
    if not _vol_filter:
        raise HTTPException(status_code=503, detail="波动率过滤器未初始化")
    return _vol_filter.get_status()


@app.get("/api/config")
async def get_config():
    """当前配置"""
    if not _config:
        raise HTTPException(status_code=503, detail="配置未加载")
    return {
        "symbols": _config.symbols,
        "leverage": _config.leverage,
        "margin_mode": _config.margin_mode,
        "risk_per_trade": _config.risk_per_trade,
        "max_daily_trades": _config.max_daily_trades,
        "max_daily_loss": _config.max_daily_loss,
        "max_consecutive_losses": _config.max_consecutive_losses,
        "max_holding_time_secs": _config.max_holding_time_secs,
        "maker_fee": _config.maker_fee,
        "taker_fee": _config.taker_fee,
        "slippage_bps": _config.slippage_bps,
        "tp1_rr": _config.tp1_rr,
        "tp2_rr": _config.tp2_rr,
        "tp1_close_pct": _config.tp1_close_pct,
        "sl_atr_buffer": _config.sl_atr_buffer,
        "volatility_filter_enabled": _config.volatility_filter_enabled,
        "volatility_atr_daily_threshold": _config.volatility_atr_daily_threshold,
        "trailing_atr_mult": _config.trailing_atr_mult,
        "quiet_mode": _config.quiet_mode,
        "emergency_close_delay_secs": _config.emergency_close_delay_secs,
    }


class ConfigReloadResponse(BaseModel):
    status: str
    message: str


@app.post("/api/config/reload")
async def reload_config():
    """热重载配置"""
    if not _bot_instance:
        raise HTTPException(status_code=503, detail="机器人未启动")
    try:
        from config import load_config
        new_cfg = load_config()
        # 更新可热更新的配置
        _bot_instance.cfg.quiet_mode = new_cfg.quiet_mode
        _bot_instance.cfg.max_daily_trades = new_cfg.max_daily_trades
        _bot_instance.cfg.max_daily_loss = new_cfg.max_daily_loss
        _bot_instance.cfg.max_consecutive_losses = new_cfg.max_consecutive_losses
        _bot_instance.cfg.max_holding_time_secs = new_cfg.max_holding_time_secs
        _bot_instance.cfg.risk_per_trade = new_cfg.risk_per_trade
        _bot_instance.cfg.trailing_atr_mult = new_cfg.trailing_atr_mult
        _bot_instance.cfg.volatility_filter_enabled = new_cfg.volatility_filter_enabled
        _bot_instance.cfg.volatility_atr_daily_threshold = new_cfg.volatility_atr_daily_threshold
        return ConfigReloadResponse(status="ok", message="配置已热更新")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置重载失败: {str(e)}")


@app.post("/api/emergency/cancel")
async def cancel_emergency_close():
    """取消紧急平仓"""
    if not _bot_instance:
        raise HTTPException(status_code=503, detail="机器人未启动")
    for symbol, exe in _executors.items():
        if exe.cancel_emergency_close():
            return {"status": "ok", "message": f"{symbol} 紧急平仓已取消"}
    return {"status": "ok", "message": "没有正在进行的紧急平仓"}


# ──────────────────── 策略管理 API ────────────────────


_STRATEGIES = {
    "po3": {
        "id": "po3",
        "name": "PO3/AMD",
        "description": "剥头皮策略 - 基于 K 线形态的突破交易",
        "author": "QuantOS",
        "version": "2.4.0",
        "simulated_capital": 1000.0,
        "parameters": {
            "leverage": {"type": "int", "default": 30, "min": 1, "max": 100},
            "risk_per_trade": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.1},
            "tp1_rr": {"type": "float", "default": 2.2},
            "tp2_rr": {"type": "float", "default": 3.0},
            "acc_bars": {"type": "int", "default": 10},
            "manip_atr_mult": {"type": "float", "default": 0.5},
        }
    },
    "orderflow": {
        "id": "orderflow",
        "name": "Order Flow",
        "description": "订单流+资金流策略 - 订单块/流动性扫取/失衡区/吸收",
        "author": "QuantOS",
        "version": "1.0.0",
        "simulated_capital": 1000.0,
        "parameters": {
            "ob_lookback": {"type": "int", "default": 10},
            "min_volume_mult": {"type": "float", "default": 1.5},
            "tp1_rr": {"type": "float", "default": 1.5},
            "tp2_rr": {"type": "float", "default": 2.5},
        }
    },
    "grid": {
        "id": "grid",
        "name": "网格策略",
        "description": "均值回归网格交易",
        "author": "Coming Soon",
        "version": "1.0.0",
        "simulated_capital": 1000.0,
        "parameters": {}
    },
    "dca": {
        "id": "dca",
        "name": "定投策略",
        "description": "Dollar Cost Averaging 定投",
        "author": "Coming Soon",
        "version": "1.0.0",
        "simulated_capital": 1000.0,
        "parameters": {}
    },
}

_ACTIVE_STRATEGIES = ["po3"]  # 支持多策略同时运行


@app.get("/api/strategies")
async def get_strategies():
    """获取所有可用策略"""
    return {
        "strategies": _STRATEGIES,
        "active": _ACTIVE_STRATEGIES,
    }


@app.get("/api/strategy/current")
async def get_current_strategy():
    """获取当前运行中的策略"""
    return {
        "active": _ACTIVE_STRATEGIES,
        "details": {sid: _STRATEGIES.get(sid) for sid in _ACTIVE_STRATEGIES},
    }


from pydantic import BaseModel


class StrategySwitchRequest(BaseModel):
    strategy_id: str
    action: str = "toggle"


@app.post("/api/strategy/switch")
async def switch_strategy(request: StrategySwitchRequest):
    """切换策略（支持多策略同时运行）"""
    strategy_id = request.strategy_id
    action = request.action
    
    if strategy_id not in _STRATEGIES:
        raise HTTPException(status_code=400, detail=f"策略 {strategy_id} 不存在")
    
    if action == "enable":
        if strategy_id not in _ACTIVE_STRATEGIES:
            _ACTIVE_STRATEGIES.append(strategy_id)
            logger.info(f"策略启用: {strategy_id}")
    elif action == "disable":
        if strategy_id in _ACTIVE_STRATEGIES:
            _ACTIVE_STRATEGIES.remove(strategy_id)
            logger.info(f"策略禁用: {strategy_id}")
    elif action == "toggle":
        if strategy_id in _ACTIVE_STRATEGIES:
            _ACTIVE_STRATEGIES.remove(strategy_id)
        else:
            _ACTIVE_STRATEGIES.append(strategy_id)
    
    return {"success": True, "active": _ACTIVE_STRATEGIES}


@app.post("/api/strategy/capital")
async def update_strategy_capital(strategy_id: str, capital: float):
    """更新策略模拟资金"""
    if strategy_id not in _STRATEGIES:
        raise HTTPException(status_code=400, detail=f"策略 {strategy_id} 不存在")
    
    if capital < 0:
        raise HTTPException(status_code=400, detail="模拟资金不能为负数")
    
    _STRATEGIES[strategy_id]["simulated_capital"] = capital
    logger.info(f"策略 {strategy_id} 模拟资金更新为: {capital} USDT")
    
    return {"success": True, "strategy_id": strategy_id, "simulated_capital": capital}


@app.get("/api/strategy/compare")
async def compare_strategies():
    """策略对比数据"""
    comparison = {}
    for sid, strategy in _STRATEGIES.items():
        is_active = sid in _ACTIVE_STRATEGIES
        comparison[sid] = {
            "name": strategy["name"],
            "active": is_active,
            "trades_today": 0 if is_active else None,
            "pnl": 0 if is_active else None,
            "win_rate": 0 if is_active else None,
        }
    
    return {
        "strategies": _STRATEGIES,
        "active": _ACTIVE_STRATEGIES,
        "comparison": comparison,
    }


@app.get("/api/backtest/results")
async def get_backtest_results():
    """回测结果列表"""
    data_dir = Path("data")
    if not data_dir.exists():
        return []
    results = []
    for f in sorted(data_dir.glob("backtest_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["file"] = f.name
                results.append(data)
        except Exception:
            pass
    return results


# ──────────────────── 独立运行模式 ────────────────────


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """
    独立启动 API 服务（无机器人实例，仅展示历史数据）
    使用方式：python -m backend.api.app
    """
    import uvicorn
    logger.info(f"[API] 启动 FastAPI 服务 http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_api_server()
