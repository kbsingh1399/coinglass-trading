import json

data = json.load(open('Engine_1_trade_logs.json'))
trades = data.get('trades', [])
today = [t for t in trades if '2026-08-15' in str(t.get('entry_time', ''))]
closed_today = [t for t in today if t.get('exit_price')]
open_t = [t for t in today if not t.get('exit_price')]
pnl = sum(t.get('pnl_usd', 0) for t in closed_today)

print('=== TODAY STATUS (2026-08-15) ===')
print(f'Open positions : {len(open_t)}')
print(f'Closed trades  : {len(closed_today)}')
print(f'PnL today      : USD {pnl:.2f}')
print()
print('--- CLOSED TRADES ---')
for t in closed_today:
    tid = str(t.get('trade_id', '?'))[:45]
    reason = str(t.get('exit_reason', '?'))
    p = t.get('pnl_usd', 0)
    print(f'  {tid:47} | {reason:8} | USD {p:+.2f}')
print()
print('--- OPEN TRADES ---')
for t in open_t:
    tid = str(t.get('trade_id', '?'))[:45]
    lp = t.get('live_pnl_usd', 0)
    print(f'  {tid:47} | live_pnl USD {lp:+.2f}')
print()
print('Meta:', json.dumps(data.get('metadata', {}), indent=2))
