import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

NY = ZoneInfo("America/New_York")
target_day = datetime(2026, 7, 16, tzinfo=NY)  
start = target_day.replace(hour=9, minute=25)   
end = target_day.replace(hour=10, minute=5)  

rq = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame(1, TimeFrameUnit.Minute),
    start=start,
    end=end
)

bars = client.get_stock_bars(rq).df
print(bars.head())

ts_index = bars.index.get_level_values("timestamp")
diffs = ts_index.to_series().diff().dropna()
gaps = diffs[diffs > timedelta(minutes=1)]
if len(gaps) > 0:
    print(f"Found {len(gaps)} gap(s) larger than 1 minute -- note this, IEX feed can be sparse:")
    print(gaps)
else:
    print("No gaps found in this sample window.")

