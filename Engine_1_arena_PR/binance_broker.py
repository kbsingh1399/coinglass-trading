"""
Binance Futures Execution Broker for Engine_1.
Pure Binance Futures perpetual swap execution. No MT5 dependencies.
Supports Dry-Run (paper trading) and Live Futures trading via REST API.
"""

import os
import time
import math
from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN, InvalidOperation
import hmac
import hashlib
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from enum import Enum

class PosState(str, Enum):
    OPEN = "OPEN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"
log = logging.getLogger("BinanceBroker")

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

TAKER_FEE = float(os.environ.get("BINANCE_TAKER_FEE", "0.0004"))    # 0.040 %
MAKER_FEE = float(os.environ.get("BINANCE_MAKER_FEE", "-0.0002"))   # -0.020 % rebate (maker rebate is negative)


def _load_env():
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


_load_env()


class BinanceBroker:
    """Binance Futures perpetual swap execution engine."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1.0, 3.0, 5.0]

    def get_position_state(self, symbol: str) -> Tuple[PosState, float]:
        res = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True, max_retries=1)
        if res is None:
            return PosState.UNKNOWN, 0.0
        try:
            for p in res:
                if p.get("symbol") == symbol:
                    amt = float(p.get("positionAmt", 0.0))
                    return (PosState.OPEN if amt != 0.0 else PosState.FLAT), amt
        except Exception:
            return PosState.UNKNOWN, 0.0
        return PosState.UNKNOWN, 0.0

    def __init__(
        self,
        dry_run: bool = True,
        account_size: float = 5000.0,
        risk_pct: float = 0.005,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        use_testnet: bool = False,
    ):
        self.dry_run = dry_run
        self.account_size = account_size
        self.risk_pct = risk_pct
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("BINANCE_SECRET_KEY", "")
        self.use_testnet = use_testnet or os.environ.get("BINANCE_USE_TESTNET", "").lower() == "true"

        if self.use_testnet:
            self.base_url = "https://testnet.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"

        self.symbol_rules: Dict[str, dict] = {}
        self.valid_perpetuals: set = set()
        self.active_orders: Dict[str, dict] = {}
        self.time_offset = 0

        # Fee Optimization Tuning parameters
        self.post_only_timeout_secs: float = 3.0
        self.min_profit_notional: float = 0.10
        self.split_notional_thresh: float = 5000.0
        self.max_slices: int = 3
        self.inter_slice_delay_secs: float = 1.0

        log.info(
            f"BinanceBroker initialized (dry_run={self.dry_run}, "
            f"testnet={self.use_testnet}, base_url={self.base_url})"
        )

    def _sign_params(self, params: dict) -> dict:
        params["timestamp"] = int((time.time() * 1000) + self.time_offset)
        params["recvWindow"] = 60000
        query_str = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _backoff_sleep(self, seconds: float):
        """Non-blocking wait loop to keep event loops responsive without blocking thread pools."""
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.01)

    def _request(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, signed: bool = True,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """Make REST request to Binance Futures API with retry logic."""
        params = params or {}
        headers = {}

        for attempt in range(max_retries):
            req_params = dict(params)
            if signed:
                if not self.api_key or not self.secret_key:
                    log.error("[Binance] Missing API key or secret key for signed request.")
                    return None
                req_params = self._sign_params(req_params)
                headers = {"X-MBX-APIKEY": self.api_key}

            query_str = urllib.parse.urlencode(req_params)
            url = f"{self.base_url}{endpoint}"
            data = None

            if method in ("GET", "DELETE"):
                if query_str:
                    url = f"{url}?{query_str}"
            elif method in ("POST", "PUT"):
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                data = query_str.encode("utf-8")

            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res_bytes = resp.read()
                    return json.loads(res_bytes.decode("utf-8"))

            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8") if hasattr(e, "read") else str(e)

                if e.code in (429, 418):
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Rate limited ({e.code}). Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue

                if e.code >= 500:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Server error {e.code}. Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue

                # Timestamp drift: re-sync and retry once
                if "-1021" in err_msg and attempt == 0:
                    log.warning("[Binance] Timestamp drift detected, re-syncing server time...")
                    self._sync_server_time()
                    continue

                log.error(f"[Binance API Error] {method} {endpoint}: {e.code} — {err_msg}")
                return None

            except Exception as e:
                if attempt < max_retries - 1:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    log.warning(f"[Binance] Network error: {e}. Retry {attempt+1}/{max_retries} in {wait}s...")
                    self._backoff_sleep(wait)
                    continue
                log.error(f"[Binance Request Failed] {method} {endpoint}: {e}")
                return None

        log.error(f"[Binance] All {max_retries} retries exhausted for {method} {endpoint}")
        return None

    def _sync_server_time(self):
        try:
            res = self._request("GET", "/fapi/v1/time", signed=False, max_retries=1)
            if res and "serverTime" in res:
                self.time_offset = res["serverTime"] - int(time.time() * 1000)
        except Exception:
            pass

    def connect(self) -> bool:
        """Sync server time and fetch exchange info precision rules."""
        try:
            self._sync_server_time()
            log.info(f"[Binance] Connected. Server time offset: {self.time_offset}ms")

            info = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
            if info and "symbols" in info:
                for s in info["symbols"]:
                    sym = s["symbol"]
                    price_prec = s.get("pricePrecision", 2)
                    qty_prec = s.get("quantityPrecision", 3)
                    min_qty = "0.001"
                    step_size = "0.001"
                    tick_size = "0.01"

                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            min_qty = str(f.get("minQty", "0.001"))
                            step_size = str(f.get("stepSize", "0.001"))
                        elif f.get("filterType") == "PRICE_FILTER":
                            tick_size = str(f.get("tickSize", "0.01"))

                    self.symbol_rules[sym] = {
                        "price_prec": price_prec,
                        "qty_prec": qty_prec,
                        "min_qty": min_qty,
                        "step_size": step_size,
                        "tick_size": tick_size,
                    }

                    if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING":
                        self.valid_perpetuals.add(sym)

                log.info(f"[Binance] Loaded rules for {len(self.symbol_rules)} contracts, "
                         f"{len(self.valid_perpetuals)} active perpetuals.")

            if not self.dry_run:
                bal, eq = self.get_account_balance_and_equity()
                log.info(f"[Binance] Account Balance: ${bal:,.2f} | Equity: ${eq:,.2f}")
                self._cancel_all_account_orders()
            return True
        except Exception as e:
            log.error(f"[Binance Connect Failed] {e}")
            return False

    def ensure_connected(self) -> bool:
        return True

    def is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol is a valid, actively trading Binance Futures perpetual."""
        if not self.valid_perpetuals:
            return symbol in self.symbol_rules
        return symbol in self.valid_perpetuals

    def get_account_balance_and_equity(self) -> Tuple[float, float]:
        details = self.get_account_details()
        return details["balance"], details["equity"]

    def get_account_details(self) -> Dict[str, float]:
        """Fetch USDT-specific balance, equity, and unrealized PnL."""
        if self.dry_run:
            return {"balance": self.account_size, "equity": self.account_size, "unrealized_pnl": 0.0}

        res = self._request("GET", "/fapi/v2/account", signed=True)
        if res:
            usdt_bal = 0.0
            usdt_eq = 0.0
            usdt_upnl = 0.0
            for asset in res.get("assets", []):
                if asset.get("asset") == "USDT":
                    usdt_bal = float(asset.get("walletBalance", 0.0))
                    usdt_eq = float(asset.get("marginBalance", 0.0))
                    usdt_upnl = float(asset.get("unrealizedProfit", 0.0))
                    break
            if usdt_bal == 0.0:
                usdt_bal = float(res.get("totalWalletBalance", 0.0))
                usdt_eq = float(res.get("totalMarginBalance", 0.0))
                usdt_upnl = float(res.get("totalUnrealizedProfit", 0.0))
            return {"balance": usdt_bal, "equity": usdt_eq, "unrealized_pnl": usdt_upnl}
        return {"balance": 0.0, "equity": 0.0, "unrealized_pnl": 0.0}

    def _round_step(self, val, step, direction: str = "nearest") -> Decimal:
        val_d = Decimal(str(val))
        step_d = Decimal(str(step))
        if step_d <= Decimal('0'):
            return val_d

        scaled = val_d / step_d
        if direction == "down":
            rounded = scaled.quantize(Decimal('1'), rounding=ROUND_DOWN)
        elif direction == "up":
            rounded = scaled.quantize(Decimal('1'), rounding=ROUND_UP)
        else:
            rounded = scaled.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN)
            
        res = rounded * step_d
        return res.quantize(step_d.normalize())

    def _format_price(self, symbol: str, price, direction: str = "nearest") -> Decimal:
        """Round price to exchange tick size (PRICE_FILTER), not just decimal precision."""
        rules = self.symbol_rules.get(symbol)
        if rules and "tick_size" in rules:
            return self._round_step(price, rules["tick_size"], direction)
        prec = rules["price_prec"] if rules else 2
        val_d = Decimal(str(price))
        fmt = Decimal('10') ** -prec
        return val_d.quantize(fmt, rounding=ROUND_HALF_EVEN)

    def _format_qty(self, symbol: str, qty) -> Decimal:
        rules = self.symbol_rules.get(symbol, {"qty_prec": 3, "step_size": "0.001", "min_qty": "0.001"})
        step = str(rules["step_size"])
        min_q = Decimal(str(rules["min_qty"]))
        formatted = self._round_step(qty, step)
        return max(formatted, min_q)

    def _place_algo_conditional(
        self, symbol: str, side: str, order_type: str, trigger_price, label: str
    ) -> Optional[dict]:
        """Place a conditional algo order (SL or TP) on Binance Futures."""
        if self.dry_run:
            log.info(f"[Binance SIM] Dry run attached {label} conditional order @ {trigger_price}")
            return {"algoId": 99999, "status": "NEW"}
        pr_str = str(self._format_price(symbol, trigger_price))
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "triggerPrice": pr_str,
            "stopPrice": pr_str,
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "priceProtect": "true",
            "algoType": "CONDITIONAL",
        }
        res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        # -4120: already active, -4138: algo with same closePosition direction exists
        if res and isinstance(res, dict) and res.get("code") in (-4120, -4138):
            log.info(f"[BINANCE LIVE] {label} already active on exchange (code {res.get('code')})")
            return {"status": "ALREADY_ACTIVE"}

        if res and ("algoId" in res or "clientAlgoId" in res or "orderId" in res) and "code" not in res:
            log.info(f"[BINANCE LIVE] Attached {label}: {pr_str} (algoId={res.get('algoId', res.get('orderId'))})")
            return res
        else:
            log.warning(f"[Binance] {label} placement failed or returned unrecognized response: {res}")
            return None

    def place_entry_limit_post_only(self, symbol: str, side: str,
                                     quantity: float, price: float) -> Optional[dict]:
        """Post-only LIMIT order (timeInForce=GTX) to earn maker rebate."""
        qty = self._format_qty(symbol, quantity)
        pr = self._format_price(symbol, price)
        if self.dry_run:
            order_id = int(time.time() * 1000) % 10_000_000
            log.info(f"[DRY-RUN] LIMIT+GTX {side} {symbol} qty={qty:.4f} "
                     f"@ {pr:.4f} (maker rebate: {MAKER_FEE*100:+.3f}%)")
            return {"orderId": order_id, "symbol": symbol, "side": side,
                    "type": "LIMIT", "origQty": str(qty), "status": "FILLED",
                    "avgPrice": str(pr), "timeInForce": "GTX"}

        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': 'LIMIT',
            'timeInForce': 'GTX',
            'quantity': qty,
            'price': pr,
            'newOrderRespType': 'RESULT',
        }
        result = self._request('POST', '/fapi/v1/order', params=params, signed=True)
        if not result or result.get('error'):
            log.warning(f"[Binance] LIMIT+GTX {side} {symbol} @ {pr:.4f}: {result}")
            return None
        log.info(f"[Binance] LIMIT+GTX {side} {symbol} "
                 f"orderId={result.get('orderId')} status={result.get('status')} "
                 f"(maker rebate: {MAKER_FEE*100:+.3f}%)")
        return result

    def _fetch_order(self, symbol: str, order_id: int) -> dict:
        """Fetch an order state. GET /fapi/v1/order"""
        if self.dry_run:
            return {'status': 'FILLED', 'executedQty': '1.0', 'cumQuote': '1.0'}
        params = {'symbol': symbol, 'orderId': order_id}
        result = self._request('GET', '/fapi/v1/order', params=params, signed=True)
        return result if result and not result.get('error') else {}

    def _check_order_filled(self, symbol: str, order_id: int) -> bool:
        """Deprecated: use _fetch_order directly."""
        res = self._fetch_order(symbol, order_id)
        return res.get('status') == 'FILLED'

    def _cancel_limit_order(self, symbol: str, order_id: int) -> bool:
        """Cancel an unfilled limit order. DELETE /fapi/v1/order"""
        if self.dry_run:
            return True
        params = {'symbol': symbol, 'orderId': order_id}
        result = self._request('DELETE', '/fapi/v1/order', params=params, signed=True)
        return bool(result and not result.get('error'))

    def _validate_profit_threshold(self, symbol: str, entry_price: float,
                                    tp: float, sl: float, quantity: float,
                                    direction: int) -> Tuple[bool, str]:
        """Reject trades where expected net PnL < 2x round-trip fees."""
        notional = quantity * entry_price
        total_fee = notional * abs(TAKER_FEE) * 2

        slippage_bps = 5.0 if symbol in {"NATGASUSDT","CLUSDT","XAGUSDT","XAUUSDT"} else 2.0
        est_slippage = notional * slippage_bps / 10000.0
        min_cost = total_fee + est_slippage

        tp_dist = abs(tp - entry_price)
        if tp_dist <= 0:
            return False, f"Invalid TP distance: {tp_dist:.6f}"

        gross_profit = quantity * tp_dist
        net_profit = gross_profit - min_cost

        if net_profit < self.min_profit_notional:
            return False, (
                f"Profit gate: net=${net_profit:.4f} < min=${self.min_profit_notional:.2f} "
                f"(gross=${gross_profit:.4f} fee=${total_fee:.4f} slip=${est_slippage:.4f})"
            )

        sl_dist = abs(entry_price - sl)
        if sl_dist <= 0:
            return False, f"Invalid SL distance: {sl_dist:.6f}"

        max_loss = quantity * sl_dist + min_cost
        rr_after_fees = net_profit / max_loss if max_loss > 0 else 0
        if rr_after_fees < 0.5:
            return False, f"Profit gate: R:R after fees={rr_after_fees:.2f} < 0.5"

        return True, "ok"

    def _slice_quantity(self, symbol: str, quantity, entry_price) -> list:
        """Split large orders (notional >= $5K) into <=3 equal slices."""
        qty_d = Decimal(str(quantity))
        entry_d = Decimal(str(entry_price))
        notional = float(qty_d * entry_d)
        
        if notional < self.split_notional_thresh or self.max_slices <= 1:
            return [qty_d]

        rules = self.symbol_rules.get(symbol, {"step_size": "0.001", "min_qty": "0.001"})
        step_size = Decimal(str(rules.get("step_size", "0.001")))

        n_slices = min(self.max_slices, max(2, int(notional / 2500)))
        
        # round slice_qty to step_size
        slice_qty_raw = qty_d / Decimal(n_slices)
        slice_qty = (slice_qty_raw / step_size).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN) * step_size
        slice_qty = slice_qty.quantize(step_size.normalize())

        if slice_qty < step_size:
            return [qty_d]

        slices = [slice_qty] * (n_slices - 1)
        remainder = qty_d - sum(slices)
        if remainder > Decimal('0'):
            remainder_rounded = (remainder / step_size).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN) * step_size
            slices.append(remainder_rounded.quantize(step_size.normalize()))

        log.info(f"[Binance] Slicing {symbol} qty={float(qty_d):.4f} "
                 f"(notional=${notional:,.0f}) -> {len(slices)} slices")
        return slices

    def execute_trade(
        self,
        binance_symbol: str,
        direction: int,
        bin_entry: float,
        bin_sl: float,
        bin_tp: float,
        strategy: str,
        risk_capital: float,
    ) -> Optional[dict]:
        """Execute trade on Binance Futures with Maker-Only GTX limits & order slicing."""
        stop_dist = abs(bin_entry - bin_sl)
        if stop_dist <= 0 or bin_entry <= 0:
            return None

        if not self.is_valid_symbol(binance_symbol):
            log.error(f"[Binance] {binance_symbol} is not a valid active perpetual. Rejecting trade.")
            return None

        qty = self._format_qty(binance_symbol, Decimal(str(risk_capital)) / Decimal(str(stop_dist)))
        entry_price = self._format_price(binance_symbol, bin_entry)
        sl_price = self._format_price(binance_symbol, bin_sl)
        tp_price = self._format_price(binance_symbol, bin_tp)

        if self.dry_run:
            log.info(f"[Binance SIM] Executed dry run trade {binance_symbol} qty={qty} @ ${entry_price}")
            return {
                "symbol": binance_symbol,
                "order_id": int(time.time() * 1000),
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "lot": qty,
                "is_pending": False,
            }

        # ── GATE 1: Profit Threshold ────────────────────────────
        passes, reason = self._validate_profit_threshold(
            binance_symbol, entry_price, tp_price, sl_price, qty, direction)
        if not passes:
            log.warning(f"[Binance] Trade REJECTED — {reason}")
            return None

        # ── GATE 2: Slicing ───────────────────────────────────────
        slices = self._slice_quantity(binance_symbol, qty, entry_price)
        n_slices = len(slices)

        side = "BUY" if direction == 1 else "SELL"
        opposite_side = "SELL" if direction == 1 else "BUY"

        ask_px = 0.0
        bid_px = 0.0

        # ── GATE 3: Latency + Spread Guard Pre-Check ─────────────
        SPREAD_REJECT_THRESHOLD = 0.0012  # 0.12% max bid-ask spread
        try:
            ticker = self._request(
                "GET", "/fapi/v1/ticker/bookTicker",
                params={"symbol": binance_symbol}, signed=False, max_retries=2
            )
            if ticker and "askPrice" in ticker and "bidPrice" in ticker:
                ask_px = float(ticker["askPrice"])
                bid_px = float(ticker["bidPrice"])
                if ask_px > 0 and bid_px > 0:
                    # ── Spread check: reject if market is too wide ──
                    spread = (ask_px - bid_px) / bid_px
                    if spread > SPREAD_REJECT_THRESHOLD:
                        log.error(
                            f"[BINANCE SPREAD REJECT] {binance_symbol} "
                            f"bid={bid_px:.4f} ask={ask_px:.4f} "
                            f"spread={spread:.4%} > {SPREAD_REJECT_THRESHOLD:.3%}. "
                            f"Aborting — illiquid spike detected."
                        )
                        return None

                    # ── Drift check ───────────────────────────────
                    if not self.dry_run and not getattr(self, 'skip_drift_check', False):
                        current_price = ask_px if direction == 1 else bid_px
                        drift = abs(current_price - bin_entry) / bin_entry
                        if drift > 0.0015:
                            log.error(
                                f"[BINANCE DRIFT REJECT] {binance_symbol} "
                                f"drift {drift:.4%} > 0.15% limit. Aborting."
                            )
                            return None
        except Exception as e:
            log.warning(
                f"[Binance] Latency/spread guard check failed, "
                f"proceeding anyway: {e}"
            )

        entry_result = None
        total_filled_qty = 0.0
        all_order_ids = []

        # ── Dynamic GTX limit offset driven by live bookTicker ──────
        # Uses the real bid/ask from the spread-guard fetch above so
        # maker orders anchor at the true market, not a stale signal
        # price. Offset scales with observed spread so wide markets
        # still get filled as maker.
        rules = self.symbol_rules.get(binance_symbol, {"tick_size": 0.01})
        tick_size = rules.get("tick_size", 0.01)

        # Determine anchor: prefer live market price over signal price
        live_ask = ask_px if ask_px > 0 else entry_price
        live_bid = bid_px if bid_px > 0 else entry_price
        spread_ticks = max(1, int((live_ask - live_bid) / tick_size + 0.5))
        # Scale offset: 1 tick in tight markets, up to 3 ticks in wide ones
        offset_ticks = min(3, max(1, spread_ticks // 2))
        anchor = live_bid if direction == 1 else live_ask
        offset = tick_size * offset_ticks

        limit_price = self._format_price(
            binance_symbol,
            anchor - offset if direction == 1 else anchor + offset
        )
        log.info(
            f"[Binance] GTX limit @ {limit_price} (anchor={'bid' if direction==1 else 'ask'}="
            f"{anchor:.4f}, spread={spread_ticks}ticks, offset={offset_ticks}ticks)"
        )

        total_cum_quote = 0.0

        for slice_idx, slice_qty in enumerate(slices):
            if slice_idx > 0:
                self._backoff_sleep(self.inter_slice_delay_secs)

            # Replaced GTX and MARKET fallback with IOC limit and slippage collar
            max_slip_bps = 50.0
            if side == "BUY":
                base_px = live_ask if live_ask > 0 else entry_price
                collar_px = base_px * (1.0 + max_slip_bps / 10000.0)
                ioc_px = self._format_price(binance_symbol, collar_px, "up")
            else:
                base_px = live_bid if live_bid > 0 else entry_price
                collar_px = base_px * (1.0 - max_slip_bps / 10000.0)
                ioc_px = self._format_price(binance_symbol, collar_px, "down")

            ioc_params = {
                "symbol": binance_symbol,
                "side": side,
                "type": "LIMIT",
                "timeInForce": "IOC",
                "price": ioc_px,
                "quantity": self._format_qty(binance_symbol, slice_qty),
                "newClientOrderId": f"E1_{strategy}_{int(time.time_ns() % 1_000_000_000)}"
            }
            ioc_result = self._request("POST", "/fapi/v1/order", params=ioc_params, signed=True)
            
            if ioc_result and "orderId" in ioc_result:
                fetched_ioc = self._fetch_order(binance_symbol, ioc_result["orderId"])
                exec_qty = float(fetched_ioc.get("executedQty", 0.0))
                if fetched_ioc.get("status") in ("FILLED", "PARTIALLY_FILLED") and exec_qty > 0:
                    entry_result = fetched_ioc
                    total_filled_qty += exec_qty
                    total_cum_quote += float(fetched_ioc.get("cumQuote", 0.0))
                    all_order_ids.append(int(ioc_result["orderId"]))
                    log.info(f"[Binance] IOC limit filled slice {slice_idx+1}/{n_slices}")
                else:
                    log.error(f"[Binance] IOC limit order {ioc_result['orderId']} failed to fill (Status: {fetched_ioc.get('status')}, ExecQty: {exec_qty}) for slice {slice_idx+1}")
                    if total_filled_qty <= Decimal("0"):
                        return None
                    break
            else:
                log.error(f"[Binance] IOC order POST failed for slice {slice_idx+1}")
                if total_filled_qty <= Decimal("0"):
                    return None
                break

        if total_filled_qty <= Decimal("0"):
            return None

        # Determine average execution price (VWAP)
        avg_price = (total_cum_quote / total_filled_qty) if total_filled_qty > Decimal("0") and total_cum_quote > Decimal("0") else entry_price
        if avg_price == 0.0:
            avg_price = entry_price

        # Dollar-distance SL/TP locking
        sl_dist = abs(entry_price - sl_price)
        tp_dist = abs(tp_price - entry_price)

        if direction == 1:
            final_sl = self._format_price(binance_symbol, avg_price - sl_dist, "down")
            final_tp = self._format_price(binance_symbol, avg_price + tp_dist, "nearest")
        else:
            final_sl = self._format_price(binance_symbol, avg_price + sl_dist, "up")
            final_tp = self._format_price(binance_symbol, avg_price - tp_dist, "nearest")

        # Removed blanket cancel_all_orders to protect other strategies' stops

        sl_res = None
        try:
            sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", final_sl, "SL")
        except Exception as e:
            log.warning(f"[Binance] SL algo order exception: {e}")

        sl_confirmed = False
        if sl_res and ("algoId" in sl_res or "clientAlgoId" in sl_res or "orderId" in sl_res):
            # NAKED GUARD Enhancement: Explicitly poll openAlgoOrders to confirm SL is physically resting
            for attempt in range(3):
                self._backoff_sleep(0.5)
                try:
                    open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
                    has_stop = any(
                        a.get("orderType") in ("STOP_MARKET", "STOP") or a.get("type") in ("STOP_MARKET", "STOP")
                        for a in (open_algos or []) if isinstance(a, dict)
                    )
                    if has_stop:
                        sl_confirmed = True
                        break
                except Exception as e:
                    log.debug(f"[Binance] Polling SL confirmation failed: {e}")
                log.warning(f"[Binance] SL not found on book yet. Retrying {attempt+1}/3...")

        if not sl_confirmed:
            log.critical(f"[BINANCE NAKED GUARD] SL placement failed or not confirmed resting! Closing market entry for {binance_symbol}")
            self.close_position(binance_symbol, "NAKED_GUARD_SL_FAILED")
            return None

        # Determine execution type for post-mortem slippage analysis
        execution_type = "MARKET"
        if entry_result and entry_result.get("timeInForce") == "GTX" and entry_result.get("status") == "FILLED":
            execution_type = "GTX_MAKER"
        elif entry_result and entry_result.get("timeInForce") == "GTX":
            execution_type = "GTX_MAKER"

        log.info(f"[BINANCE LIVE SUCCESS] Fill: {binance_symbol} {side} {total_filled_qty} @ ${avg_price:,.2f} slices={n_slices} exec_type={execution_type}")

        return {
            "symbol": binance_symbol,
            "order_id": all_order_ids[0] if all_order_ids else int(time.time()),
            "entry_price": avg_price,
            "sl_price": final_sl,
            "tp_price": final_tp,
            "lot": total_filled_qty,
            "basis_pct": 0.0,
            "is_pending": False,
            "execution_type": execution_type,
        }

    def _cancel_all_account_orders(self):
        """Cancel all open standard and algo orders across all symbols on startup."""
        if self.dry_run:
            return
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", signed=True)
            if open_algos and isinstance(open_algos, list):
                for algo in open_algos:
                    if "algoId" in algo:
                        self._request("DELETE", "/fapi/v1/algoOrder", params={"algoId": algo["algoId"]}, signed=True)
                log.info(f"[Binance] Cleaned up {len(open_algos)} stale algo orders on account.")
        except Exception as e:
            log.warning(f"[Binance] Exception in startup algo cleanup: {e}")

    def _cancel_all_orders(self, binance_symbol: str):
        """Cancel all open orders and algo orders for a symbol."""
        if self.dry_run:
            return
        self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": binance_symbol}, signed=True)
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            algo_list = []
            if open_algos and isinstance(open_algos, dict):
                algo_list = open_algos.get("orders", [])
            elif open_algos and isinstance(open_algos, list):
                algo_list = open_algos
            for algo in algo_list:
                if "algoId" in algo:
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"algoId": algo["algoId"]}, signed=True)
        except Exception as e:
            log.warning(f"[BINANCE LIVE] Failed to cancel algo orders for {binance_symbol}: {e}")

    def modify_sltp(self, binance_symbol: str, position_ticket: int, sl: float, tp: float) -> bool:
        """Modify open SL/TP orders using PLACE-THEN-CANCEL pattern (zero naked window).
        
        New SL/TP orders are placed FIRST, then old orders are cancelled by specific ID.
        The position is protected at all times during the transition.
        """
        if self.dry_run:
            log.info(f"[BINANCE DRY RUN] Modify SLTP {binance_symbol} SL={sl} TP={tp}")
            return True

        positions = self._request("GET", "/fapi/v2/account", signed=True)
        if not positions or "positions" not in positions:
            return False

        pos_amt = 0.0
        for p in positions["positions"]:
            if p["symbol"] == binance_symbol:
                pos_amt = float(p["positionAmt"])
                break

        if pos_amt == 0.0:
            log.warning(f"[Binance] Cannot modify SL/TP: No open position for {binance_symbol}")
            return False

        opposite_side = "SELL" if pos_amt > 0 else "BUY"
        formatted_sl = self._format_price(binance_symbol, sl)
        formatted_tp = self._format_price(binance_symbol, tp)

        # ── PLACE-THEN-CANCEL: Zero Naked Window Pattern ──────────────
        # Step 1: Snapshot old algo order IDs (do NOT cancel yet)
        old_algo_ids = []
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            if open_algos and isinstance(open_algos, list):
                old_algo_ids = [a["algoId"] for a in open_algos if "algoId" in a]
        except Exception as e:
            log.warning(f"[Binance] Exception fetching old algo orders: {e}")

        # Step 2: Place NEW SL first — old SL still protects position
        new_sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", formatted_sl, "NEW_SL")
        sl_placed = bool(new_sl_res and ("algoId" in new_sl_res or "clientAlgoId" in new_sl_res or "orderId" in new_sl_res))
        # DEEP-AUDIT FIX: duplicate/collision must not count as placed; verify existing stop, then no-op.
        if new_sl_res and new_sl_res.get("status") == "ALREADY_ACTIVE" and not sl_placed:
            remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            has_stop = any(
                a.get("orderType") in ("STOP_MARKET", "STOP") or a.get("type") in ("STOP_MARKET", "STOP")
                for a in (remaining or []) if isinstance(a, dict)
            )
            if has_stop:
                log.info(f"[Binance] SL heartbeat for {binance_symbol}: existing exchange stop active (protected no-op).")
                return True

        # FIX (Fable5-2.3): TP on exchange intentionally skipped.
        # Trail ratchet is the only exit; hard TP on Binance truncates right-tail winners.
        # self._place_algo_conditional(binance_symbol, opposite_side, "TAKE_PROFIT_MARKET", formatted_tp, "NEW_TP")

        # Step 4: Cancel old algo orders by specific ID (preserves newly placed orders)
        if sl_placed:
            for algo_id in old_algo_ids:
                try:
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": binance_symbol, "algoId": algo_id}, signed=True)
                except Exception as e:
                    log.warning(f"[Binance] Failed to cancel old algo order {algo_id}: {e}")
        else:
            log.warning(f"[Binance] New SL placement failed. Skipping cancellation of old algo orders to maintain protection.")

        # Step 5: If new SL failed, old SL was NOT cancelled (still active). Only emergency
        # close if BOTH old and new SL are confirmed missing.
        if not sl_placed:
            try:
                remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
                has_stop = any(
                    a.get("orderType") in ("STOP_MARKET", "STOP") or a.get("type") in ("STOP_MARKET", "STOP")
                    for a in (remaining or [])
                )
                if not has_stop:
                    log.critical(f"[BINANCE NAKED GUARD] New SL failed AND no old SL remains for {binance_symbol} — emergency closing!")
                    self.close_position(binance_symbol, "SL_MOD_FAILED")
                    return False
                else:
                    log.warning(f"[Binance] New SL failed but old SL still active for {binance_symbol}. Will retry next tick.")
                    return False
            except Exception:
                log.critical(f"[BINANCE NAKED GUARD] Cannot verify old SL status for {binance_symbol} — emergency closing!")
                self.close_position(binance_symbol, "SL_MOD_FAILED")
                return False

        log.info(f"[BINANCE LIVE] SLTP Modified for {binance_symbol}: SL={formatted_sl} TP={formatted_tp} (place-then-cancel)")
        return True

    def close_position(self, symbol: str, reason: str = "ENGINE_EXIT") -> bool:
        """Close open position on Binance Futures with Market order."""
        if self.dry_run:
            log.info(f"[BINANCE DRY RUN] Close position symbol={symbol}, reason={reason}")
            return True

        # Always cancel all open standard & algo orders for this symbol first
        self._cancel_all_orders(symbol)

        positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
        if not positions:
            log.warning(f"[BINANCE LIVE] positionRisk returned empty for {symbol} (timeout?). Retrying once...")
            time.sleep(1.0)
            positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
            if not positions:
                log.error(f"[BINANCE LIVE] positionRisk failed twice for {symbol}. Cannot close safely.")
                return False

        for p in positions:
            if p["symbol"] != symbol:
                continue
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0.0:
                side = "SELL" if amt > 0 else "BUY"
                close_qty = abs(amt)
                res = self._request("POST", "/fapi/v1/order", params={
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": close_qty,
                    "reduceOnly": "true",
                }, signed=True)

                if res and "orderId" in res:
                    log.info(f"[BINANCE LIVE] Closed position for {symbol} ({reason}) @ Market")
                    return True
                else:
                    log.error(f"[BINANCE LIVE] Failed to close position for {symbol}")
                    return False
        return True

    def get_position_history_profit(self, position_ticket: int) -> Tuple[float, float]:
        """Fetch realized profit and exit price from user trades."""
        if self.dry_run:
            return 0.0, 0.0
        return 0.0, 0.0

    def get_last_fill(self, symbol: str) -> Optional[dict]:
        """Fetch the most recent fill for a symbol from user trades for reconciliation."""
        if self.dry_run:
            return None
        try:
            res = self._request("GET", "/fapi/v1/userTrades",
                                params={"symbol": symbol, "limit": 1}, signed=True)
            if res and isinstance(res, list) and len(res) > 0:
                t = res[0]
                return {
                    "price": float(t.get("price", 0)),
                    "qty": float(t.get("qty", 0)),
                    "commission": abs(float(t.get("commission", 0))),
                    "time": t.get("time", 0),
                    "side": t.get("side", ""),
                    "realizedPnl": float(t.get("realizedPnl", 0)),
                }
        except Exception as e:
            log.warning(f"[BINANCE] get_last_fill failed for {symbol}: {e}")
        return None
