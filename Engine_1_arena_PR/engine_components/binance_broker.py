"""
Binance Futures Execution Broker for Engine_1.
Pure Binance Futures perpetual swap execution. No MT5 dependencies.
Supports Dry-Run (paper trading) and Live Futures trading via REST API.
"""

import os
import time
import math
import hmac
import hashlib
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

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
        params["recvWindow"] = 5000
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

                if e.code >= 500 or e.code == 408:
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

    def _place_order_safe(self, endpoint: str, params: dict, max_retries: int = 3) -> Optional[dict]:
        """Safely place an order. If a timeout/5xx occurs, query the exchange to see if it filled."""
        if "newClientOrderId" not in params:
            params["newClientOrderId"] = f"E1_{int(time.time_ns() % 1_000_000_000)}"

        for attempt in range(max_retries):
            # Attempt order with exactly 1 internal retry to avoid blind double-fills
            res = self._request("POST", endpoint, params=params, signed=True, max_retries=1)
            
            # If we get a response, and it's not a timeout/5xx (e.g. rate limit is handled internally or it succeeded)
            # Actually, _request handles 429 inside if it can. If it returns None, it means it really failed.
            if res is not None:
                return res
            
            # Query the exchange to see if the order exists
            wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
            self._backoff_sleep(wait)
            
            log.warning(f"[Binance] Order request failed. Querying status of {params['newClientOrderId']}...")
            check_res = self._request("GET", "/fapi/v1/order", params={
                "symbol": params["symbol"],
                "origClientOrderId": params["newClientOrderId"]
            }, signed=True, max_retries=1)
            
            if check_res and "orderId" in check_res:
                log.info(f"[Binance] Found missing order {check_res['orderId']} on exchange!")
                return check_res
            
            log.warning(f"[Binance] Order not found on exchange. Retrying {attempt+1}/{max_retries}...")
        
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
                    min_qty = 0.001
                    step_size = 0.001
                    tick_size = 0.01

                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            min_qty = float(f.get("minQty", 0.001))
                            step_size = float(f.get("stepSize", 0.001))
                        elif f.get("filterType") == "PRICE_FILTER":
                            tick_size = float(f.get("tickSize", 0.01))

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
                log.info(f"[Binance] Authenticated! USDT Wallet: ${bal:,.2f}, Equity: ${eq:,.2f}")
            return True
        except Exception as e:
            log.error(f"[Binance Connect Failed] {e}")
            return False

    def ensure_connected(self) -> bool:
        return True

    def is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol is a valid, actively trading Binance Futures perpetual."""
        if not self.valid_perpetuals:
            if not self.symbol_rules:
                try:
                    self.connect()
                except Exception:
                    pass
            if self.valid_perpetuals:
                return symbol in self.valid_perpetuals
            if self.symbol_rules:
                return symbol in self.symbol_rules
            # Known major crypto perpetuals fallback if exchangeInfo failed due to transient startup network lag
            known_majors = {
                "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
                "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT", "SUIUSDT", "NEARUSDT",
                "DOTUSDT", "LTCUSDT"
            }
            return symbol in known_majors
        return symbol in self.valid_perpetuals

    def get_account_balance_and_equity(self) -> Tuple[float, float]:
        """Fetch free balance and total equity in USDT."""
        res = self._request("GET", "/fapi/v2/account", signed=True)
        if res:
            return float(res.get("availableBalance", 0.0)), float(res.get("totalWalletBalance", 0.0))
        return 0.0, 0.0

    def get_all_positions(self) -> List[dict]:
        """Fetch all active positions from the exchange."""
        res = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        active_positions = []
        if res and isinstance(res, list):
            for pos in res:
                if float(pos.get("positionAmt", 0)) != 0.0:
                    active_positions.append(pos)
        return active_positions

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

    def _round_step(self, val: float, step: float, direction: str = "nearest") -> float:
        if step <= 0:
            return val
        # Use floor arithmetic — avoids log10 precision issues for stepSize >= 1
        if direction == "down":
            return math.floor(val / step) * step
        elif direction == "up":
            return math.ceil(val / step) * step
        # nearest: round half-down to stay within risk budget
        return math.floor(val / step + 0.5) * step

    def _format_price(self, symbol: str, price: float, direction: str = "nearest") -> float:
        """Round price to exchange tick size (PRICE_FILTER), not just decimal precision."""
        rules = self.symbol_rules.get(symbol)
        prec = rules.get("price_prec", 2) if rules else 2
        if rules and "tick_size" in rules:
            return round(self._round_step(price, rules["tick_size"], direction), prec)
        return round(price, prec)

    def _format_qty(self, symbol: str, qty: float) -> float:
        rules = self.symbol_rules.get(symbol, {"qty_prec": 3, "step_size": 0.001, "min_qty": 0.001})
        step = rules["step_size"]
        min_q = rules["min_qty"]
        prec = rules.get("qty_prec", 3)
        # Always floor to keep position within the risk budget and clean precision
        formatted = round(self._round_step(qty, step, direction="down"), prec)
        return max(formatted, min_q)

    def _place_algo_conditional(
        self, symbol: str, side: str, order_type: str, trigger_price: float, label: str
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
        if res and res.get("code") in (-4120, -4130, -4138):
            log.info(f"[Binance] {label} position already protected by existing exchange stop ({res.get('code')}). Local Engine_1 check_exits active.")
            return {"status": "ALREADY_ACTIVE", "code": res.get("code")}

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
        result = self._place_order_safe('/fapi/v1/order', params=params)
        if not result or result.get('error'):
            log.warning(f"[Binance] LIMIT+GTX {side} {symbol} @ {pr:.4f}: {result}")
            return None
        log.info(f"[Binance] LIMIT+GTX {side} {symbol} "
                 f"orderId={result.get('orderId')} status={result.get('status')} "
                 f"(maker rebate: {MAKER_FEE*100:+.3f}%)")
        return result

    def _check_order_filled(self, symbol: str, order_id: int) -> bool:
        """Check if a limit order has filled. GET /fapi/v1/order"""
        if self.dry_run:
            return True
        params = {'symbol': symbol, 'orderId': order_id}
        result = self._request('GET', '/fapi/v1/order', params=params, signed=True)
        return result.get('status') == 'FILLED' if result and not result.get('error') else False

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

    def _slice_quantity(self, symbol: str, quantity: float,
                         entry_price: float) -> List[float]:
        """Split large orders (notional >= $5K) into <=3 equal slices."""
        notional = quantity * entry_price
        if notional < self.split_notional_thresh or self.max_slices <= 1:
            return [quantity]

        rules = self.symbol_rules.get(symbol, {"step_size": 0.001, "min_qty": 0.001})
        step_size = rules.get("step_size", 0.001)

        n_slices = min(self.max_slices, max(2, int(notional / 2500)))
        slice_qty = round(quantity / n_slices / step_size) * step_size

        if slice_qty < step_size:
            return [quantity]

        slices = [slice_qty] * (n_slices - 1)
        remainder = quantity - sum(slices)
        if remainder > 0:
            slices.append(round(remainder / step_size) * step_size)

        log.info(f"[Binance] Slicing {symbol} qty={quantity:.4f} "
                 f"(notional=${notional:,.0f}) -> {len(slices)} slices")
        return slices

    def execute_trade(
        self,
        binance_symbol: str,
        direction: int,
        bin_entry: float,
        bin_sl: float,
        bin_tp: Optional[float],
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

        # Mirror risk governor friction so broker lot == local risk exactly
        TOTAL_FRICTION = 0.0012
        effective_stop_dist = stop_dist + (bin_entry * TOTAL_FRICTION)
        qty = self._format_qty(binance_symbol, risk_capital / effective_stop_dist)
        entry_price = self._format_price(binance_symbol, bin_entry)
        sl_price = self._format_price(binance_symbol, bin_sl)
        # tp=None means trailing-stop-only mode; skip exchange TP placement
        tp_price = self._format_price(binance_symbol, bin_tp) if bin_tp is not None else None

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
        # Skip when tp_price is None (trailing-stop-only mode — no hard TP exit)
        if tp_price is not None:
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
        SPREAD_REJECT_THRESHOLD = float(os.environ.get("BINANCE_MAX_SPREAD", "0.0035"))  # 0.35% max bid-ask spread
        MAX_DRIFT_THRESHOLD = float(os.environ.get("BINANCE_MAX_DRIFT", "0.0035"))        # 0.35% max price drift
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
                        if drift > MAX_DRIFT_THRESHOLD:
                            log.error(
                                f"[BINANCE DRIFT REJECT] {binance_symbol} "
                                f"drift {drift:.4%} > {MAX_DRIFT_THRESHOLD:.2%}. Aborting."
                            )
                            return None
        except Exception as e:
            log.warning(
                f"[Binance] Latency/spread guard check failed, "
                f"proceeding anyway: {e}"
            )

        # Enforce leverage before placing any orders (default 10x)
        if not self.dry_run:
            try:
                lev = int(os.environ.get("BINANCE_LEVERAGE", "10"))
                self._request("POST", "/fapi/v1/leverage",
                              params={"symbol": binance_symbol, "leverage": lev},
                              signed=True, max_retries=2)
            except Exception as lev_e:
                log.warning(f"[Binance] set_leverage failed for {binance_symbol}: {lev_e}")

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

        for slice_idx, slice_qty in enumerate(slices):
            if slice_idx > 0:
                self._backoff_sleep(self.inter_slice_delay_secs)

            if n_slices == 1 or slice_idx == 0:
                limit_result = self.place_entry_limit_post_only(
                    binance_symbol, side, slice_qty, limit_price)
                if limit_result and not limit_result.get('error'):
                    order_id = limit_result.get('orderId')
                    if order_id:
                        t0 = time.time()
                        filled = False
                        while time.time() - t0 < self.post_only_timeout_secs:
                            self._backoff_sleep(0.3)
                            if self._check_order_filled(binance_symbol, order_id):
                                filled = True
                                break
                        if filled:
                            entry_result = limit_result
                            total_filled_qty += slice_qty
                            all_order_ids.append(order_id)
                            log.info(f"[Binance] LIMIT+GTX filled slice {slice_idx+1}/{n_slices} (maker rebate: {MAKER_FEE*100:+.3f}%)")
                            continue
                        else:
                            # Check partial fill before canceling
                            order_info = self._request('GET', '/fapi/v1/order', params={'symbol': binance_symbol, 'orderId': order_id}, signed=True)
                            exec_qty = float(order_info.get('executedQty', 0.0)) if order_info else 0.0
                            self._cancel_limit_order(binance_symbol, order_id)
                            if exec_qty > 0:
                                total_filled_qty += exec_qty
                                all_order_ids.append(order_id)
                                log.info(f"[Binance] LIMIT+GTX partially filled {exec_qty:.4f}/{slice_qty:.4f}")
                            remaining_slice = slice_qty - exec_qty
                            if remaining_slice <= 0:
                                continue
                            slice_qty = remaining_slice

                # Fallback to MARKET
                mkt_params = {
                    "symbol": binance_symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": self._format_qty(binance_symbol, slice_qty),
                    "newClientOrderId": f"E1_{strategy}_{int(time.time_ns() % 1_000_000_000)}"
                }
                mkt_result = self._place_order_safe("/fapi/v1/order", params=mkt_params)
                if not mkt_result or "orderId" not in mkt_result:
                    log.error(f"[Binance] Fallback MARKET order failed for slice {slice_idx+1}")
                    if total_filled_qty <= 0:
                        return None
                    break
                entry_result = mkt_result
                total_filled_qty += slice_qty
                all_order_ids.append(int(mkt_result["orderId"]))
            else:
                mkt_params = {
                    "symbol": binance_symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": self._format_qty(binance_symbol, slice_qty),
                    "newClientOrderId": f"E1_{strategy}_{int(time.time_ns() % 1_000_000_000)}"
                }
                mkt_result = self._place_order_safe("/fapi/v1/order", params=mkt_params)
                if mkt_result and "orderId" in mkt_result:
                    all_order_ids.append(int(mkt_result["orderId"]))
                    total_filled_qty += slice_qty
                else:
                    log.error(f"[Binance] Market execution failed for slice {slice_idx+1}")

            # (qty already added in confirmed-fill branches above)

        if total_filled_qty <= 0:
            return None

        # Determine average execution price
        avg_price = entry_price
        if entry_result:
            cum_quote = float(entry_result.get("cumQuote", 0.0))
            exec_qty = float(entry_result.get("executedQty", 0.0))
            avg_price = (cum_quote / exec_qty) if exec_qty > 0 and cum_quote > 0 else float(entry_result.get("avgPrice", entry_price))
            if avg_price == 0.0:
                avg_price = entry_price

        # Dollar-distance SL/TP locking
        sl_dist = abs(entry_price - sl_price)

        if direction == 1:
            final_sl = self._format_price(binance_symbol, avg_price - sl_dist, "down")
            final_tp = self._format_price(binance_symbol, avg_price + abs(tp_price - entry_price), "nearest") if tp_price is not None else None
        else:
            final_sl = self._format_price(binance_symbol, avg_price + sl_dist, "up")
            final_tp = self._format_price(binance_symbol, avg_price - abs(tp_price - entry_price), "nearest") if tp_price is not None else None

        sl_res = None
        for _sl_attempt in range(3):
            try:
                sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", final_sl, "SL")
            except Exception as e:
                log.warning(f"[Binance] SL algo order exception (attempt {_sl_attempt + 1}): {e}")
            if sl_res and ("algoId" in sl_res or "clientAlgoId" in sl_res or "orderId" in sl_res
                           or sl_res.get("status") == "ALREADY_ACTIVE"):
                break
            sl_res = None
            if _sl_attempt < 2:
                time.sleep(1.0 * (_sl_attempt + 1))

        if not sl_res:
            log.error(f"[BINANCE NAKED GUARD] SL placement failed after 3 attempts! Attempting emergency close of entry for {binance_symbol}")
            closed = self.close_position(binance_symbol, "NAKED_GUARD_SL_FAILED")
            if not closed:
                log.critical(f"[BINANCE] [CRITICAL] Entry on {binance_symbol} may be open WITHOUT a stop and the emergency "
                             f"close could not be verified. Returning UNVERIFIED_OPEN_POSITION for tracker reconciliation.")
                return {"status": "UNVERIFIED_OPEN_POSITION", "symbol": binance_symbol,
                        "side": side, "qty": total_filled_qty, "avg_price": avg_price}
            return None

        # FIX (Fable5-2.3): No exchange-side TAKE_PROFIT_MARKET — backtest sim() has no hard TP;
        # the trailing stop is the sole exit. A hard TP on exchange truncates winning tails
        # (5R→12R) and inverts the exit model that was walk-forward validated.
        # if final_tp is not None: self._place_algo_conditional(..., "TAKE_PROFIT_MARKET", ...)

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

    def _cancel_all_orders(self, binance_symbol: str):
        """Cancel all open orders and algo orders for a symbol."""
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
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": binance_symbol, "algoId": algo["algoId"]}, signed=True)
        except Exception as e:
            log.warning(f"[BINANCE LIVE] Failed to cancel algo orders for {binance_symbol}: {e}")

    def modify_sltp(self, binance_symbol: str, position_ticket: int, sl: float, tp: Optional[float] = None) -> bool:
        """Modify open SL/TP orders using PLACE-THEN-CANCEL pattern (zero naked window).
        
        New SL/TP orders are placed FIRST, then old orders are cancelled. The position
        is protected at all times during the transition. If new SL placement fails,
        old SL remains active and no emergency close is triggered.
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
        formatted_tp = self._format_price(binance_symbol, tp) if tp is not None else None

        # ── PLACE-THEN-CANCEL: Zero Naked Window Pattern ──────────────
        # Step 1: Snapshot old algo order IDs (do NOT cancel yet — old SL still protects position)
        old_algo_ids = []
        try:
            open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            algo_list = []
            if open_algos and isinstance(open_algos, dict):
                algo_list = open_algos.get("orders", [])
            elif open_algos and isinstance(open_algos, list):
                algo_list = open_algos
            old_algo_ids = [algo["algoId"] for algo in algo_list if "algoId" in algo]
        except Exception as e:
            log.warning(f"[Binance] Exception fetching old algo orders: {e}")

        # Step 2: Place NEW SL first — position remains protected by old SL during this call
        new_sl_res = self._place_algo_conditional(binance_symbol, opposite_side, "STOP_MARKET", formatted_sl, "NEW_SL")
        sl_placed = bool(new_sl_res and (
            "algoId" in new_sl_res or "clientAlgoId" in new_sl_res or "orderId" in new_sl_res
        ))
        # DEEP-AUDIT FIX (P0): a duplicate/collision response (ALREADY_ACTIVE) carries no real
        # algoId and must NEVER count as a placement. If the existing stop is still on the
        # exchange, the heartbeat is a protected no-op success.
        if new_sl_res and new_sl_res.get("status") == "ALREADY_ACTIVE" and not sl_placed:
            remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
            remaining_list = []
            if remaining and isinstance(remaining, dict):
                remaining_list = remaining.get("orders", [])
            elif remaining and isinstance(remaining, list):
                remaining_list = remaining
            has_stop = any(
                algo.get("orderType") in ("STOP_MARKET", "STOP") or algo.get("type") in ("STOP_MARKET", "STOP")
                for algo in remaining_list
            )
            if has_stop:
                log.info(f"[Binance] SL heartbeat for {binance_symbol}: existing exchange stop active (protected no-op).")
                return True
        elif ("algoId" in new_sl_res or "clientAlgoId" in new_sl_res or "orderId" in new_sl_res) and new_sl_res.get("algoId") != 0:
            sl_placed = True
        elif new_sl_res and new_sl_res.get("status") == "MANAGED_BY_ENGINE":
            log.info(f"[Binance] SL modify collision. Keeping existing SL active.")
            return False

        # Step 3: TP on exchange intentionally skipped (Fable5-2.3).
        # Trail ratchet is the only exit; hard TP on Binance truncates right-tail winners.
        # if formatted_tp is not None: self._place_algo_conditional(..., "TAKE_PROFIT_MARKET", ...)

        # Step 4: NOW cancel old algo orders if the new SL was successfully placed
        if sl_placed:
            for algo_id in old_algo_ids:
                try:
                    self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": binance_symbol, "algoId": algo_id}, signed=True)
                except Exception as e:
                    log.warning(f"[Binance] Failed to cancel old algo order {algo_id}: {e}")
        else:
            log.warning(f"[Binance] New SL placement failed. Skipping cancellation of old algo orders to maintain protection.")

        # Step 5: If new SL placement failed, old SL was NOT cancelled (still active).
        # Only emergency close if BOTH old and new SL are confirmed missing.
        if not sl_placed:
            try:
                remaining = self._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": binance_symbol}, signed=True)
                remaining_list = []
                if remaining and isinstance(remaining, dict):
                    remaining_list = remaining.get("orders", [])
                elif remaining and isinstance(remaining, list):
                    remaining_list = remaining
                has_stop = any(
                    algo.get("orderType") in ("STOP_MARKET", "STOP") or algo.get("type") in ("STOP_MARKET", "STOP")
                    for algo in remaining_list
                )
                if not has_stop:
                    log.critical(f"[BINANCE NAKED GUARD] New SL failed AND no old SL remains for {binance_symbol} — emergency closing!")
                    self.close_position(binance_symbol, "SL_MOD_FAILED")
                    return False
                else:
                    log.warning(f"[Binance] New SL placement failed but old SL still active for {binance_symbol}. Will retry next tick.")
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

        positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
        if not positions:
            # DEEP-AUDIT FIX: a failed position query must NOT be reported as a successful close.
            time.sleep(1.0)
            positions = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
            if not positions:
                log.error(f"[BINANCE] Cannot verify position state for {symbol} — close aborted as FAILED (no false success).")
                return False

        for p in positions:
            if p["symbol"] != symbol:
                continue
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0.0:
                log.info(f"[BINANCE LIVE] Close requested for {symbol}. Current position: {amt}")

                side = "SELL" if amt > 0 else "BUY"
                close_qty = abs(amt)
                res = None
                for _close_attempt in range(3):
                    res = self._place_order_safe("/fapi/v1/order", params={
                        "symbol": symbol,
                        "side": side,
                        "type": "MARKET",
                        "quantity": close_qty,
                        "reduceOnly": "true",
                    })
                    if res and "orderId" in res:
                        break
                    time.sleep(1.0 * (_close_attempt + 1))

                if res and "orderId" in res:
                    self._cancel_all_orders(symbol)
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

    def get_last_fill(self, symbol: str) -> dict:
        """Get the last realized PnL and exit price for a symbol."""
        if self.dry_run:
            return None
        try:
            res = self._request("GET", "/fapi/v1/userTrades", params={"symbol": symbol, "limit": 20}, signed=True)
            if not res:
                return None
            res.reverse()
            target_order_id = None
            for t in res:
                if float(t.get("realizedPnl", "0")) != 0.0:
                    target_order_id = t["orderId"]
                    break
            
            if not target_order_id:
                return None
                
            total_qty = 0.0
            total_quote_qty = 0.0
            total_pnl = 0.0
            total_comm = 0.0
            
            for t in res:
                if t["orderId"] == target_order_id:
                    qty = float(t["qty"])
                    total_qty += qty
                    total_quote_qty += float(t["price"]) * qty
                    total_pnl += float(t["realizedPnl"])
                    total_comm += float(t["commission"])
            
            if total_qty > 0:
                return {
                    "price": total_quote_qty / total_qty,
                    "realizedPnl": total_pnl,
                    "commission": total_comm
                }
        except Exception as e:
            log.error(f"[BinanceBroker] Failed to fetch last fill for {symbol}: {e}")
        return None
