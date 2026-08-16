import sys
import re

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

with open('live_engine_output.txt', 'r', encoding='utf-8', errors='replace') as f:
    f.seek(0, 2)
    size = f.tell()
    f.seek(max(0, size - 10000))
    tail = f.read()

lines = tail.splitlines()
# Strip box-drawing / ANSI escape sequences for clean output
ansi = re.compile(r'\x1b\[[0-9;]*m')
for line in lines[-80:]:
    clean = ansi.sub('', line)
    try:
        print(clean)
    except Exception:
        print(repr(clean))
