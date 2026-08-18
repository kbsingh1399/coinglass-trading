import json
import os
import time
from typing import Dict, Any

class RufloMemory:
    """
    Agentic Memory Store: Learns from past trades to optimize future decisions.
    """
    def __init__(self, memory_file: str = "ruflo_memory.json"):
        self.memory_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", memory_file)
        self.memories = []
        self._load_memory()

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    self.memories = json.load(f)
            except Exception:
                self.memories = []

    def save_memory(self, trade_data: Dict[str, Any]):
        self.memories.append(trade_data)
        # Keep last 1000 memories to prevent bloat
        if len(self.memories) > 1000:
            self.memories = self.memories[-1000:]
        
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memories, f, indent=4)

    def query_similar_context(self, symbol: str, strategy: str, macro: int, vol_regime: float) -> Dict[str, Any]:
        """Finds past performance in similar market regimes."""
        relevant = [m for m in self.memories if m.get("symbol") == symbol and m.get("strategy") == strategy]
        
        if not relevant:
            return {"win_rate": 0.5, "sample_size": 0}
            
        wins = sum(1 for m in relevant if m.get("pnl_usd", 0) > 0)
        return {
            "win_rate": wins / len(relevant),
            "sample_size": len(relevant)
        }

class RufloSwarm:
    """
    Swarm Coordinator: Evaluates ML signals against Macro conditions and Memory.
    """
    def __init__(self, memory: RufloMemory):
        self.memory = memory

    def evaluate_signal(self, symbol: str, strategy: str, direction: int, entry_price: float, sl: float, tp: float, atr: float, macro: int, vol_regime: float) -> float:
        """
        Returns a confidence score between 0.0 and 1.0.
        If confidence is < 0.4, the trade should be rejected by the engine.
        """
        base_confidence = 0.5
        
        # 1. Macro Context Evaluation
        if direction == macro:
            base_confidence += 0.2
        elif macro != 0:
            base_confidence -= 0.15
            
        # 2. Volatility Evaluation
        # If volatility is extremely high, confidence drops for mean reversion
        if strategy == "S4_Mean_Reversion" and vol_regime > 2.0:
            base_confidence -= 0.2
            
        # 3. Memory Evaluation (Self-Learning)
        mem_stats = self.memory.query_similar_context(symbol, strategy, macro, vol_regime)
        if mem_stats["sample_size"] > 5:
            # Shift confidence towards historical win rate
            base_confidence = (base_confidence + mem_stats["win_rate"]) / 2
            
        # Cap confidence between 0.1 and 0.99
        return max(0.1, min(0.99, base_confidence))

class RufloBridge:
    def __init__(self):
        self.memory = RufloMemory()
        self.swarm = RufloSwarm(self.memory)
        print("[RufloBridge] Agentic Harness initialized. Memory and Swarm active.")
        
    def validate_trade(self, symbol: str, strategy: str, direction: int, entry_price: float, sl: float, tp: float, atr: float, macro: int, vol_regime: float) -> dict:
        score = self.swarm.evaluate_signal(symbol, strategy, direction, entry_price, sl, tp, atr, macro, vol_regime)
        
        return {
            "confidence": score,
            "approved": score >= 0.4,
            "reason": "Swarm validated against macro and memory." if score >= 0.4 else f"Low confidence ({score:.2f}) from Swarm."
        }
        
    def log_trade_closure(self, trade: dict):
        """Called when a trade is closed to learn from it."""
        try:
            summary = {
                "trade_id": trade.get("trade_id"),
                "symbol": trade.get("symbol"),
                "strategy": trade.get("strategy"),
                "direction": trade.get("direction"),
                "pnl_usd": trade.get("pnl_usd"),
                "pnl_pct": trade.get("pnl_pct"),
                "macro": trade.get("macro"),
                "vol_regime": trade.get("vol_regime"),
                "timestamp": time.time()
            }
            self.memory.save_memory(summary)
            print(f"[RufloBridge] Trade {trade.get('trade_id')} added to agentic memory.")
        except Exception as e:
            print(f"[RufloBridge] Error logging trade closure: {e}")

# Global singleton
ruflo_bridge = RufloBridge()
