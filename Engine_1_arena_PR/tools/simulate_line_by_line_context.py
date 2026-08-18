"""
Context-Based Line-by-Line Execution Tracer & State Simulator.
Hooks into Python's execution frame to trace every executed line, variable mutations, and async context states.
"""

import sys
import time
import inspect
from pathlib import Path

class ContextSimulator:
    def __init__(self, target_module_name: str = ""):
        self.target_module = target_module_name
        self.step_counter = 0
        self.last_locals = {}

    def trace_lines(self, frame, event, arg):
        if event != "line":
            return self.trace_lines
            
        filename = frame.f_code.co_filename
        if self.target_module and self.target_module not in filename:
            return self.trace_lines

        self.step_counter += 1
        line_no = frame.f_lineno
        func_name = frame.f_code.co_name
        current_locals = {k: v for k, v in frame.f_locals.items() if not k.startswith("__")}
        
        # Detect state changes / variable mutations
        mutations = {}
        for k, v in current_locals.items():
            if k not in self.last_locals or self.last_locals[k] != v:
                repr_v = repr(v)
                if len(repr_v) > 60:
                    repr_v = repr_v[:57] + "..."
                mutations[k] = repr_v
        
        self.last_locals = dict(current_locals)
        
        # Read source line content
        try:
            lines = inspect.getsourcelines(frame.f_code)[0]
            start_line = frame.f_code.co_firstlineno
            rel_idx = line_no - start_line
            code_line = lines[rel_idx].strip() if 0 <= rel_idx < len(lines) else ""
        except Exception:
            code_line = ""

        # Format trace output
        mutation_str = f" | Mutated: {mutations}" if mutations else ""
        print(f"[Step {self.step_counter:04d}] {Path(filename).name}:{line_no:<4} [{func_name}()] -> {code_line:<45}{mutation_str}", flush=True)
        return self.trace_lines

    def run(self, func, *args, **kwargs):
        print("=" * 90)
        print("  STARTING CONTEXT-BASED LINE-BY-LINE EXECUTION SIMULATION")
        print("=" * 90)
        sys.settrace(self.trace_lines)
        try:
            res = func(*args, **kwargs)
            return res
        finally:
            sys.settrace(None)
            print("=" * 90)
            print(f"  SIMULATION FINISHED — Total Steps Executed: {self.step_counter}")
            print("=" * 90)

if __name__ == "__main__":
    def sample_pipeline_calculation(price: float, volume: float, cvd: float):
        vwap = price * 1.002
        delta = volume * 0.15
        signal = "BUY" if cvd > 0 and price > vwap else "NEUTRAL"
        return {"price": price, "vwap": vwap, "signal": signal}

    sim = ContextSimulator()
    sim.run(sample_pipeline_calculation, price=95420.5, volume=1250.0, cvd=450000.0)
