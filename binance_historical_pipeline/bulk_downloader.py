import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
from datetime import datetime, timedelta

def _create_session():
    """Creates a requests session with retry strategy."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

_session = _create_session()

def download_day(symbol, date_str, data_types, interval="5m"):
    """Downloads all requested data types for a single specific day."""
    tf = interval
    for data_type in data_types:
        download_dir = os.path.join(os.getcwd(), "downloads", symbol, data_type)
        os.makedirs(download_dir, exist_ok=True)
        
        if data_type == "premiumIndexKlines":
            url = f"https://data.binance.vision/data/futures/um/daily/{data_type}/{symbol}/{tf}/{symbol}-{tf}-{date_str}.zip"
            file_name = f"{symbol}-{data_type}-{date_str}.zip"
        else:
            base_url = f"https://data.binance.vision/data/futures/um/daily/{data_type}/{symbol}/"
            file_name = f"{symbol}-{data_type}-{date_str}.zip"
            url = base_url + file_name
            
        file_path = os.path.join(download_dir, file_name)
        if data_type == "premiumIndexKlines":
            csv_name = f"{symbol}-{tf}-{date_str}.csv"
        else:
            csv_name = file_name.replace(".zip", ".csv")
        csv_path = os.path.join(download_dir, csv_name)

        
        # Check if extracted CSV already exists
        if os.path.exists(csv_path):
            continue
            
        max_attempts = 4
        success = False
        for attempt in range(max_attempts):
            try:
                response = _session.get(url, stream=True, timeout=(10, 120))
                if response.status_code == 200:
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=16384):
                            f.write(chunk)
                    
                    import zipfile
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            zip_ref.extractall(download_dir)
                    except Exception as e:
                        print(f"      [WARN] Extraction failed for {file_name} (Attempt {attempt+1}/{max_attempts}): {e}. Deleting corrupt zip.")
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        raise e
                    
                    # Cleanup zip
                    for _ in range(5):
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            break
                        except PermissionError:
                            time.sleep(1)
                    success = True
                    break
                elif response.status_code == 404:
                    # 404 means the file is not on the server, no need to retry
                    break
                else:
                    print(f"      [FAIL] {file_name} (Status: {response.status_code}) - Attempt {attempt+1}/{max_attempts}")
                    if attempt < max_attempts - 1:
                        time.sleep(5 * (attempt + 1))
            except Exception as e:
                print(f"      [WARN] Attempt {attempt+1}/{max_attempts} failed for {file_name}: {e}")
                if os.path.exists(file_path):
                    try: os.remove(file_path)
                    except: pass
                if attempt < max_attempts - 1:
                    time.sleep(5 * (attempt + 1))
        
        if not success and response.status_code != 404:
            print(f"      [ERR]  Permanently failed to download {file_name} after {max_attempts} attempts.")

def download_binance_data(symbol, start_date_str, end_date_str, data_types=["metrics", "aggTrades"], interval="5m"):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")