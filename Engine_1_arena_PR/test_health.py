import sys
import requests
import time
from Engine_1 import start_health_server_threaded, SnapshotStore

app_state = {"store": None, "binance_ws": None}
start_health_server_threaded(app_state, port=8081)
time.sleep(1)

# Request before store is initialized
print("Request 1 (store=None):")
try:
    r = requests.get("http://localhost:8081/health")
    print(r.json())
except Exception as e:
    print(f"Error: {e}")

# Initialize store
store = SnapshotStore(["BTCUSDT"])
# mock some data
store._data["BTCUSDT"].fut_cvd = 100.0
store._data["BTCUSDT"].spot_cvd = 50.0
app_state["store"] = store

# Request after store is initialized
print("Request 2 (store initialized):")
try:
    r = requests.get("http://localhost:8081/health")
    print(r.json())
except Exception as e:
    print(f"Error: {e}")
