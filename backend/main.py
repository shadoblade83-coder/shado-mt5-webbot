"""
Shado MT5 Web Bot backend.

This is a technical starter bridge between a browser dashboard and MetaTrader 5.
Default mode is paper/logging mode. Live order sending is blocked unless
LIVE_TRADING_ENABLED=true is placed in .env.
"""

from __future__ import annotations

import os
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - allows dashboard/dev without MT5 installed
    mt5 = None


LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
API_SECRET = os.getenv("API_SECRET", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="Shado MT5 Web Bot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BotConfig(BaseModel):
    symbol: str = Field(default="EURUSD", min_length=3)
    timeframe: str = Field(default="M15", pattern="^(M1|M5|M15|M30|H1|H4|D1)$")
    mode: Literal["paper", "live"] = "paper"
    lot: float = Field(default=0.01, gt=0, le=100)
    fast_sma: int = Field(default=10, ge=2, le=200)
    slow_sma: int = Field(default=30, ge=3, le=500)
    stop_loss_points: int = Field(default=200, ge=1)
    take_profit_points: int = Field(default=300, ge=1)
    max_spread_points: int = Field(default=40, ge=1)
    max_open_positions: int = Field(default=1, ge=0, le=20)
    loop_seconds: int = Field(default=30, ge=5, le=3600)


class ManualOrder(BaseModel):
    symbol: str = Field(default="EURUSD", min_length=3)
    side: Literal["buy", "sell"]
    lot: float = Field(default=0.01, gt=0, le=100)
    stop_loss_points: int = Field(default=200, ge=1)
    take_profit_points: int = Field(default=300, ge=1)
    mode: Literal["paper", "live"] = "paper"


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MT5Bridge:
    def __init__(self) -> None:
        self.initialized = False
        self.last_error: Optional[Any] = None

    def _timeframe(self, name: str) -> int:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 Python package is not available")
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        return mapping[name]

    def initialize(self) -> bool:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed or cannot load on this machine")

        if self.initialized:
            return True

        path = os.getenv("MT5_PATH") or None
        ok = mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            self.last_error = mt5.last_error()
            return False

        login_raw = os.getenv("MT5_LOGIN")
        password = os.getenv("MT5_PASSWORD")
        server = os.getenv("MT5_SERVER")
        if login_raw and password and server:
            try:
                ok = mt5.login(int(login_raw), password=password, server=server)
            except ValueError:
                ok = False
            if not ok:
                self.last_error = mt5.last_error()
                return False

        self.initialized = True
        return True

    def ensure(self) -> None:
        if not self.initialize():
            raise RuntimeError(f"Could not initialize/login to MT5: {self.last_error}")

    def status(self) -> Dict[str, Any]:
        if mt5 is None:
            return {"connected": False, "error": "MetaTrader5 package not loaded"}
        try:
            self.ensure()
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            return {
                "connected": True,
                "terminal": terminal._asdict() if terminal else None,
                "account": account._asdict() if account else None,
                "live_trading_enabled_in_env": LIVE_TRADING_ENABLED,
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc), "live_trading_enabled_in_env": LIVE_TRADING_ENABLED}

    def rates(self, symbol: str, timeframe: str, count: int = 120) -> List[Dict[str, Any]]:
        self.ensure()
        mt5.symbol_select(symbol, True)
        raw = mt5.copy_rates_from_pos(symbol, self._timeframe(timeframe), 0, count)
        if raw is None:
            raise RuntimeError(f"Could not fetch rates: {mt5.last_error()}")
        candles: List[Dict[str, Any]] = []
        for row in raw:
            candles.append(
                {
                    "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": int(row["tick_volume"]),
                    "spread": int(row["spread"]),
                }
            )
        return candles

    def tick(self, symbol: str) -> Dict[str, Any]:
        self.ensure()
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"Could not fetch tick: {mt5.last_error()}")
        return tick._asdict()

    def positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure()
        raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if raw is None:
            return []
        return [p._asdict() for p in raw]

    def send_market_order(self, order: ManualOrder) -> Dict[str, Any]:
        self.ensure()
        if order.mode == "live" and not LIVE_TRADING_ENABLED:
            raise RuntimeError("Live trading is blocked. Set LIVE_TRADING_ENABLED=true in backend/.env to unlock it.")

        symbol_info = mt5.symbol_info(order.symbol)
        if symbol_info is None:
            raise RuntimeError(f"Symbol not found: {order.symbol}")
        mt5.symbol_select(order.symbol, True)
        tick = mt5.symbol_info_tick(order.symbol)
        if tick is None:
            raise RuntimeError("No tick data available")

        point = symbol_info.point
        is_buy = order.side == "buy"
        price = tick.ask if is_buy else tick.bid
        sl = price - order.stop_loss_points * point if is_buy else price + order.stop_loss_points * point
        tp = price + order.take_profit_points * point if is_buy else price - order.take_profit_points * point

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.lot,
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 4042026,
            "comment": "Shado MT5 Web Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            # Some brokers reject one filling mode. If that happens, change this to IOC/FOK.
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        check = mt5.order_check(request)
        if check is None:
            raise RuntimeError(f"order_check failed: {mt5.last_error()}")
        if order.mode == "paper":
            return {"paper": True, "checked_request": request, "order_check": check._asdict()}

        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"order_send failed: {mt5.last_error()}")
        return result._asdict()


bridge = MT5Bridge()


def sma(values: List[float], length: int) -> float:
    if len(values) < length:
        raise ValueError("Not enough values for SMA")
    return sum(values[-length:]) / length


def crossover_signal(candles: List[Dict[str, Any]], fast_len: int, slow_len: int) -> Literal["buy", "sell", "hold"]:
    closes = [float(c["close"]) for c in candles]
    if len(closes) < slow_len + 2 or fast_len >= slow_len:
        return "hold"

    prev_fast = sum(closes[-fast_len - 1 : -1]) / fast_len
    prev_slow = sum(closes[-slow_len - 1 : -1]) / slow_len
    cur_fast = sma(closes, fast_len)
    cur_slow = sma(closes, slow_len)

    if prev_fast <= prev_slow and cur_fast > cur_slow:
        return "buy"
    if prev_fast >= prev_slow and cur_fast < cur_slow:
        return "sell"
    return "hold"


class BotController:
    def __init__(self) -> None:
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.config = BotConfig()
        self.logs: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def log(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        with self.lock:
            self.logs.append({"time": utc_now(), "event": event, "data": data or {}})
            self.logs = self.logs[-250:]

    def start(self, config: BotConfig) -> Dict[str, Any]:
        if config.fast_sma >= config.slow_sma:
            raise HTTPException(status_code=400, detail="fast_sma must be smaller than slow_sma")
        if config.mode == "live" and not LIVE_TRADING_ENABLED:
            raise HTTPException(status_code=403, detail="Live trading is locked by .env")

        if self.running:
            self.config = config
            self.log("config_updated", config.model_dump())
            return self.state()

        self.config = config
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log("bot_started", config.model_dump())
        return self.state()

    def stop(self) -> Dict[str, Any]:
        self.running = False
        self.log("bot_stopped")
        return self.state()

    def state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "config": self.config.model_dump(),
                "logs": list(reversed(self.logs[-60:])),
                "live_trading_enabled_in_env": LIVE_TRADING_ENABLED,
            }

    def _risk_ok(self, config: BotConfig) -> tuple[bool, str]:
        if mt5 is None:
            return config.mode == "paper", "MT5 not loaded; paper logging only"
        try:
            tick = bridge.tick(config.symbol)
            symbol_info = mt5.symbol_info(config.symbol)
            spread_points = int(round((tick["ask"] - tick["bid"]) / symbol_info.point)) if symbol_info else 999999
            if spread_points > config.max_spread_points:
                return False, f"Spread too high: {spread_points} points"

            open_positions = bridge.positions(config.symbol)
            if len(open_positions) >= config.max_open_positions:
                return False, f"Max open positions reached: {len(open_positions)}"
            return True, "ok"
        except Exception as exc:
            if config.mode == "paper":
                return True, f"paper mode ignoring MT5 risk read error: {exc}"
            return False, str(exc)

    def _loop(self) -> None:
        while self.running:
            cfg = self.config
            try:
                candles = bridge.rates(cfg.symbol, cfg.timeframe, max(cfg.slow_sma + 5, 80))
                signal = crossover_signal(candles, cfg.fast_sma, cfg.slow_sma)
                self.log("signal", {"symbol": cfg.symbol, "signal": signal})

                if signal != "hold":
                    ok, reason = self._risk_ok(cfg)
                    if not ok:
                        self.log("trade_blocked_by_risk", {"reason": reason})
                    else:
                        order = ManualOrder(
                            symbol=cfg.symbol,
                            side=signal,
                            lot=cfg.lot,
                            stop_loss_points=cfg.stop_loss_points,
                            take_profit_points=cfg.take_profit_points,
                            mode=cfg.mode,
                        )
                        result = bridge.send_market_order(order)
                        self.log("order_result", {"result": result})
            except Exception as exc:
                self.log("error", {"message": str(exc)})

            time.sleep(cfg.loop_seconds)


bot = BotController()


@app.get("/")
def root() -> Dict[str, str]:
    return {"name": "Shado MT5 Web Bot", "status": "ok"}


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    return bridge.status()


@app.get("/api/rates")
def api_rates(
    symbol: str = Query(default="EURUSD"),
    timeframe: str = Query(default="M15", pattern="^(M1|M5|M15|M30|H1|H4|D1)$"),
    count: int = Query(default=120, ge=10, le=1000),
) -> Dict[str, Any]:
    return {"symbol": symbol, "timeframe": timeframe, "candles": bridge.rates(symbol, timeframe, count)}


@app.get("/api/positions")
def api_positions(symbol: Optional[str] = None) -> Dict[str, Any]:
    return {"positions": bridge.positions(symbol)}


@app.post("/api/manual-order", dependencies=[Depends(require_api_key)])
def api_manual_order(order: ManualOrder) -> Dict[str, Any]:
    if order.mode == "live" and not LIVE_TRADING_ENABLED:
        raise HTTPException(status_code=403, detail="Live trading is locked by .env")
    return {"result": bridge.send_market_order(order)}


@app.post("/api/bot/start", dependencies=[Depends(require_api_key)])
def api_bot_start(config: BotConfig) -> Dict[str, Any]:
    return bot.start(config)


@app.post("/api/bot/stop", dependencies=[Depends(require_api_key)])
def api_bot_stop() -> Dict[str, Any]:
    return bot.stop()


@app.get("/api/bot/state")
def api_bot_state() -> Dict[str, Any]:
    return bot.state()
