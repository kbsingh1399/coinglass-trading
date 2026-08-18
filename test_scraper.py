import asyncio
import sys
from coinglass_scraper import EnhancedCoinglassScraper

class MockExcelPool:
    async def submit_data(self, symbol, data):
        print(f'MOCK POOL RECEIVED {len(data)} ROWS FOR {symbol}')
        for row in data[-5:]:
            print(f'  {row["timestamp"]}: L={row["liq_long"]}, S={row["liq_short"]}')

async def run_scraper():
    pool = MockExcelPool()
    scraper = EnhancedCoinglassScraper(pool, skip_seed=False)
    scraper.symbols = ['BTCUSDT'] # override symbols to just one for quick test
    try:
        await scraper.start()
        print('Scraper started.')
        await asyncio.sleep(60) # let it run for 1 min
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await scraper.stop()
        print('Scraper stopped.')

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == '__main__':
    asyncio.run(run_scraper())
