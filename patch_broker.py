import sys

with open("engine_components/binance_broker.py", "r", encoding="utf-8") as f:
    content = f.read()

get_last_fill_code = """
    def get_last_fill(self, symbol: str) -> dict:
        \"\"\"Get the last realized PnL and exit price for a symbol.\"\"\"
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
"""

if "def get_last_fill" not in content:
    content += get_last_fill_code
    with open("engine_components/binance_broker.py", "w", encoding="utf-8") as f:
        f.write(content)

with open("Engine_1.py", "r", encoding="utf-8") as f:
    e_content = f.read()

adapter_code = """
    def get_last_fill(self, symbol: str) -> dict:
        if hasattr(self.broker, "get_last_fill"):
            return self.broker.get_last_fill(symbol)
        return None
"""

if "def get_last_fill" not in e_content:
    e_content = e_content.replace(
        "def list_engine_positions(self) -> list:",
        adapter_code.strip() + "\n\n    def list_engine_positions(self) -> list:"
    )
    with open("Engine_1.py", "w", encoding="utf-8") as f:
        f.write(e_content)

print("Patched successfully")
