import json
from collections import defaultdict
from datetime import datetime

data = json.load(open('Engine_1_trade_logs.json'))
trades = data.get('trades', [])
today = [t for t in trades if '2026-08-15' in str(t.get('entry_time', ''))]
closed = [t for t in today if t.get('exit_price')]

print('=== LOSS DEEP-DIVE ANALYSIS ===')
print()

# By strategy
by_strat = defaultdict(list)
for t in closed:
    strat = t.get('strategy', '?')
    by_strat[strat].append(t)

print('--- BY STRATEGY ---')
for s, ts in sorted(by_strat.items()):
    pnl = sum(x.get('pnl_usd', 0) for x in ts)
    print(f'  {s}: {len(ts)} trades, PnL = ${pnl:.2f}')

print()
# By symbol
by_sym = defaultdict(list)
for t in closed:
    sym = t.get('symbol', '?')
    by_sym[sym].append(t)

print('--- BY SYMBOL ---')
for s, ts in sorted(by_sym.items()):
    pnl = sum(x.get('pnl_usd', 0) for x in ts)
    print(f'  {s}: {len(ts)} trades, PnL = ${pnl:.2f}')

print()
# By direction
by_dir = defaultdict(list)
for t in closed:
    d = t.get('direction', '?')
    by_dir[d].append(t)

print('--- BY DIRECTION ---')
for s, ts in sorted(by_dir.items()):
    pnl = sum(x.get('pnl_usd', 0) for x in ts)
    print(f'  {s}: {len(ts)} trades, PnL = ${pnl:.2f}')

print()
# Entry/exit detail
print('--- ENTRY/EXIT DETAIL ---')
for t in closed:
    ep = t.get('entry_price', 0)
    xp = t.get('exit_price', 0)
    sl = t.get('sl_price', 0)
    tp = t.get('tp_price', 0)
    d = t.get('direction', '?')
    sym = t.get('symbol', '?')
    pnl = t.get('pnl_usd', 0)
    et = str(t.get('entry_time', ''))[-8:]
    xt = str(t.get('exit_time', ''))[-8:]
    dur_s = 'N/A'
    try:
        entry_dt = datetime.fromisoformat(str(t.get('entry_time', '')).replace('Z',''))
        exit_dt  = datetime.fromisoformat(str(t.get('exit_time', '')).replace('Z',''))
        dur = (exit_dt - entry_dt).total_seconds() / 60
        dur_s = f'{dur:.1f}m'
    except Exception:
        pass
    sl_dist_pct = abs(sl - ep) / ep * 100 if ep and sl else 0
    print(f'  {sym:12} {d:5} entry={ep:.6g} sl={sl:.6g} ({sl_dist_pct:.2f}%) exit={xp:.6g} held={dur_s} pnl=${pnl:+.2f}')
